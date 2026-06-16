import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from agents.state import OptimizationState
from config import get_llm, settings
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
- Never require knowledge outside the transcript to evaluate a criterion
- Transcript is text-only: never infer tone, intonation, warmth, voice quality, or prosodic cues — every criterion must be derivable from the written words alone
- Adherence must be established from explicit verbal content in the transcript only — never from non-transcript actions (e.g., post-call system updates, CRM entries), implicit signals (e.g., agent hanging up), or behaviours that are not spoken in the conversation
- Evaluation is binary: the agent either adhered or did not. Never introduce partial adherence, scoring, thresholds, or weighted criteria
- Never add positional or time-bound constraints (e.g. "in the first 2 messages", "within N turns", "before the customer responds"). Message-window scoping is controlled by evaluation_type and n_messages, not the description\
"""


async def prompt_optimizer(state: OptimizationState) -> dict:
    logger.info(
        "session=%s phase=optimizing_prompts iteration=%d",
        state["session_id"], state["current_iteration"],
    )

    session_id = state["session_id"]
    records = dict(state["parameter_records"])
    below_target = state["parameters_below_target"]
    user_answers = state.get("user_answers", {})
    qid_to_param = {q["question_id"]: q["parameter_name"] for q in state.get("clarifying_questions", [])}
    iteration = state["current_iteration"]

    session_store.update(session_id, {
        "current_phase": "optimizing_prompts",
        "progress_log": list(state.get("progress_log", [])),
    })

    completed_messages: list[str] = []

    try:
        llm_config = state.get("llm_config", {})
        llm = get_llm(
            model=llm_config.get("model"),
            api_key=llm_config.get("api_key"),
            base_url=llm_config.get("base_url"),
        )
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

        rule_answers = {qid: ans for qid, ans in user_answers.items() if qid_to_param.get(qid) == rule_id}
        new_description = await _optimise_description(record, rule_answers, llm, session_id)

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


def _is_stagnant(record: dict, min_entries: int = 3) -> bool:
    history = record.get("iteration_history", [])
    if len(history) < min_entries:
        return False
    recent = [h["accuracy"] for h in history[-min_entries:]]
    # Stagnant if improvement over last N iterations is less than 3 percentage points
    return (max(recent) - min(recent)) < 0.03


async def _optimise_description(
    record: dict, user_answers: dict, llm: BaseChatModel, session_id: str
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
            "Do not change evaluation_type, n_messages, or speaker. "
            "Do NOT include any language about inapplicability, the trigger condition being absent, "
            "or 'when the scenario does not apply'. The trigger rule already handles Not Applicable "
            "automatically — the description must only specify what constitutes adherence when the "
            "scenario IS in scope."
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

    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()
