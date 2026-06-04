import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents.state import OptimizationState
from config import settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert QA rule description writer for contact centre quality evaluation.
Rule descriptions are used by an LLM evaluation system to assess conversation transcripts.

You MUST output descriptions using this exact structured format:

METRIC_NAME: <2-5 word Title Case name>
SPEAKER: <Agent | Customer>
ACTION: <verb-first single sentence describing what is evaluated>
PASS_LOGIC: <ALL | ANY>
PASS_CRITERIA:
1. <atomic observable condition, detectable from transcript text>
2. <atomic observable condition>
EXAMPLES:
PASS:
1. "<example utterance that would pass>"
2. "<example utterance that would pass>"
FAIL:
1. "<example utterance that would fail>"
2. "<example utterance that would fail>"

Format rules:
- METRIC_NAME: 2-5 words, Title Case
- SPEAKER: must exactly match the rule's speaker field (Agent or Customer)
- ACTION: starts with a verb, one sentence only
- PASS_LOGIC: ALL if every criterion must be met; ANY if at least one is sufficient
- PASS_CRITERIA: 2-5 numbered conditions; each must be observable from transcript text alone
- EXAMPLES: minimum 2 PASS and 2 FAIL utterances that would appear verbatim in a transcript
- Never use vague terms: "appropriately", "effectively", "sufficiently", "properly", "well"
- Never require knowledge outside the transcript to evaluate a criterion\
"""


def _get_generation_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0.2,
        top_p=1,
        max_completion_tokens=2000,
        timeout=120,
        api_key=settings.openai_api_key or None,
    )


async def prompt_optimizer(state: OptimizationState) -> dict:
    logger.info(
        "session=%s phase=optimizing_prompts iteration=%d",
        state["session_id"], state["current_iteration"],
    )

    session_id = state["session_id"]
    records = dict(state["parameter_records"])
    below_target = state["parameters_below_target"]
    user_answers = state.get("user_answers", {})
    iteration = state["current_iteration"]

    session_store.update(session_id, {
        "current_phase": "optimizing_prompts",
        "progress_log": list(state.get("progress_log", [])),
    })

    completed_messages: list[str] = []

    try:
        llm = _get_generation_llm()
    except Exception as exc:
        session_store.append_log(session_id, f"ERROR: Could not initialise LLM — {exc}")
        logger.error("session=%s prompt_optimizer LLM init failed: %s", session_id, exc)
        return {
            "parameter_records": records,
            "current_iteration": iteration + 1,
            "current_phase": "error",
            "progress_log": [f"LLM initialisation failed: {exc}"],
        }

    for rule_id in below_target:
        record = records[rule_id]

        session_store.append_log(session_id, f"Optimising description for {rule_id} (iteration {iteration + 1})…")

        history_entry = {
            "iteration": iteration,
            "description": record["current_description"],
            "accuracy": record["current_accuracy"],
            "precision": record["current_precision"],
            "recall": record["current_recall"],
            "f1": record["current_f1"],
        }

        new_description = await _optimise_description(record, user_answers, llm, session_id)

        records[rule_id] = {
            **record,
            "iteration_history": [*record["iteration_history"], history_entry],
            "current_description": new_description,
            "current_predictions": {},
            "optimization_notes": f"Optimised at iteration {iteration + 1}",
        }
        msg = f"Description updated for {rule_id} (iteration {iteration + 1})"
        session_store.append_log(session_id, msg)
        completed_messages.append(msg)
        logger.info("session=%s rule_id=%s description updated for iteration %d", session_id, rule_id, iteration + 1)

    return {
        "parameter_records": records,
        "current_iteration": iteration + 1,
        "current_phase": "evaluating",
        "progress_log": completed_messages,
    }


def _accuracy_trajectory(record: dict) -> str:
    history = record.get("iteration_history", [])
    if not history:
        return ""
    # Deduplicate consecutive identical accuracies (benchmarking + optimizer both append entries)
    seen: list[float] = []
    for h in history:
        if not seen or h["accuracy"] != seen[-1]:
            seen.append(h["accuracy"])
    return "Accuracy trajectory: " + " → ".join(f"{a:.0%}" for a in seen)


def _is_stagnant(record: dict, min_entries: int = 4) -> bool:
    history = record.get("iteration_history", [])
    if len(history) < min_entries:
        return False
    recent = [h["accuracy"] for h in history[-min_entries:]]
    return len(set(recent)) == 1


async def _optimise_description(
    record: dict, user_answers: dict, llm: ChatOpenAI, session_id: str
) -> str:
    rule_type = record["rule_type"]
    clarifications = "\n".join(f"- {v}" for v in user_answers.values()) if user_answers else "None"

    if rule_type == "trigger":
        constraints = (
            "The PASS_CRITERIA must remain detectable from transcript text. "
            "Do not change evaluation_type, n_messages, or speaker."
        )
    else:
        constraints = (
            "The PASS_CRITERIA must be evaluable solely from transcript evidence. "
            "Do not change evaluation_type, n_messages, or speaker."
        )

    trajectory = _accuracy_trajectory(record)
    trajectory_line = f"Accuracy history: {trajectory}\n\n" if trajectory else ""

    if _is_stagnant(record):
        rewrite_instruction = (
            "IMPORTANT: This rule has been STAGNANT — accuracy has not improved across multiple "
            "iterations. Incremental refinement is not working. You MUST make a fundamentally "
            "different change: reconsider whether PASS_CRITERIA are measuring the right observable "
            "signal, whether the ACTION statement should be reframed entirely, or whether the "
            "EXAMPLES are representative. Do NOT make small edits to the existing description — "
            "rewrite it from a different angle based on the error patterns."
        )
    else:
        rewrite_instruction = (
            "Rewrite the description in the structured format to address the identified failure patterns. "
            "Update PASS_CRITERIA to fix the specific errors identified in the RCA. "
            "Add or revise EXAMPLES to reflect the failure cases."
        )

    prompt = (
        f"Rule ID: {record['rule_id']}\n"
        f"Rule type: {rule_type} | Speaker: {record['speaker']} | "
        f"Evaluation type: {record['evaluation_type']} | n_messages: {record['n_messages']}\n\n"
        f"Current description:\n{record['current_description']}\n\n"
        f"Root cause analysis:\n{record.get('rca_findings', 'No findings available.')}\n\n"
        f"{trajectory_line}"
        f"User clarifications:\n{clarifications}\n\n"
        f"Constraints: {constraints}\n\n"
        f"{rewrite_instruction} "
        "Respond with only the structured description, no preamble."
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()
    except Exception as exc:
        logger.warning(
            "session=%s rule_id=%s optimiser LLM failed: %s",
            session_id, record["rule_id"], type(exc).__name__,
        )
        return record["current_description"]
