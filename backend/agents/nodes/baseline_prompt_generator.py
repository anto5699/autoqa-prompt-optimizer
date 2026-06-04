import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import OptimizationState
from config import get_llm
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


async def baseline_prompt_generator(state: OptimizationState) -> dict:
    logger.info("session=%s phase=generating_baselines", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "generating_baselines"})

    records = dict(state["parameter_records"])
    user_answers = state.get("user_answers", {})
    log_messages = []

    for rule_id, record in records.items():
        has_description = bool(record["current_description"].strip())
        has_clarifications = bool(user_answers)

        if not has_description:
            # No description from CSV — generate from scratch
            task = _build_generation_task(record, user_answers, mode="generate")
            response = await get_llm().ainvoke([
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=task),
            ])
            new_description = response.content.strip()
            records[rule_id] = {**record, "current_description": new_description}
            log_messages.append(f"Generated baseline description for {rule_id}")
            logger.info("session=%s generated baseline for rule_id=%s", state["session_id"], rule_id)

        elif has_clarifications:
            # Clarifications exist — rewrite from scratch anchored to user answers.
            # Prevents semantic drift when clarifications redefine the criterion entirely.
            task = _build_generation_task(record, user_answers, mode="rewrite")
            response = await get_llm().ainvoke([
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=task),
            ])
            new_description = response.content.strip()
            records[rule_id] = {**record, "current_description": new_description}
            log_messages.append(f"Rewrote description for {rule_id} using clarification answers")
            logger.info("session=%s rewrote description from clarifications for rule_id=%s", state["session_id"], rule_id)

    return {
        "parameter_records": records,
        "current_phase": "evaluating",
        "progress_log": log_messages or ["Baselines ready: using production descriptions from CSV"],
    }


def _build_generation_task(record: dict, user_answers: dict, *, mode: str) -> str:
    rule_type = record["rule_type"]
    clarifications = "\n".join(f"- {v}" for v in user_answers.values()) if user_answers else "None"

    if rule_type == "trigger":
        guidance = (
            "Write a TRIGGER rule description that detects whether a specific scenario is present:\n"
            "- PASS_CRITERIA must identify the exact condition from transcript text\n"
            "- Specify whether exact phrasing or semantic equivalents qualify\n"
            "- Identify which speaker initiates or expresses the condition\n"
            "- EXAMPLES should show transcripts that DO and DO NOT trigger the rule"
        )
    else:
        guidance = (
            "Write an ANSWER rule description that evaluates agent adherence to a quality guideline:\n"
            "- PASS_CRITERIA must state exactly what the agent must say or do\n"
            "- FAIL examples must show what 'Not Adhered' looks like in transcript text\n"
            "- Avoid partial adherence ambiguity: define clear pass/fail boundary"
        )

    if mode == "rewrite":
        preamble = (
            f"The existing description may be vague or may measure a DIFFERENT criterion than intended.\n"
            f"The user's clarifications are the authoritative definition of what this rule actually measures.\n"
            f"If the clarifications define a different criterion than the original description, "
            f"write the new description around the clarifications — not the original description.\n\n"
            f"Original description (for reference only):\n{record['current_description']}\n\n"
        )
    else:
        preamble = ""

    return (
        f"{preamble}"
        f"Rule metadata:\n"
        f"- rule_id: {record['rule_id']}\n"
        f"- rule_type: {rule_type}\n"
        f"- speaker: {record['speaker']}\n"
        f"- evaluation_type: {record['evaluation_type']}\n"
        f"- n_messages: {record['n_messages']}\n\n"
        f"User clarifications:\n{clarifications}\n\n"
        f"{guidance}\n\n"
        "Respond with only the structured description, no preamble or explanation."
    )
