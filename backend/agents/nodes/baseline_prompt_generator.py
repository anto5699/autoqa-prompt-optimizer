import asyncio
import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

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


async def baseline_prompt_generator(state: OptimizationState) -> dict:
    logger.info("session=%s phase=generating_baselines", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "generating_baselines"})

    llm_config = state.get("llm_config", {})
    llm = get_llm(
        model=llm_config.get("optimizer_model") or llm_config.get("model"),
        api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
        base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
        purpose="optimizer",
    )
    session_store.append_trace(state["session_id"], {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "node": "baseline_prompt_generator", "model": llm.model_name, "event": "start",
        "details": {"rules": len(state["parameter_records"])},
    })

    records = dict(state["parameter_records"])
    user_answers = state.get("user_answers", {})
    qid_to_param = {q["question_id"]: q["parameter_name"] for q in state.get("clarifying_questions", [])}

    semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)

    async def _process_rule(rule_id: str, record: dict) -> tuple[str, dict | None, str | None]:
        has_description = bool(record["current_description"].strip())
        rule_answers = {qid: ans for qid, ans in user_answers.items() if qid_to_param.get(qid) == rule_id}
        has_clarifications = bool(rule_answers)

        if not has_description:
            mode = "generate"
        elif has_clarifications:
            mode = "rewrite"
        elif not _is_structured(record["current_description"]):
            mode = "format"
        else:
            return rule_id, None, None

        task = _build_generation_task(record, rule_answers if mode in ("generate", "rewrite") else {}, mode=mode)
        async with semaphore:
            response = await llm.ainvoke([
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=task),
            ])
        new_description = response.content.strip()
        log_msg = {
            "generate": f"Generated baseline description for {rule_id}",
            "rewrite": f"Rewrote description for {rule_id} using clarification answers",
            "format": f"Converted {rule_id} description to structured format",
        }[mode]
        logger.info("session=%s mode=%s rule_id=%s", state["session_id"], mode, rule_id)
        return rule_id, {**record, "current_description": new_description}, log_msg

    tasks = [_process_rule(rule_id, record) for rule_id, record in records.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    log_messages = []
    for item in results:
        if isinstance(item, Exception):
            logger.warning("session=%s baseline generation error: %s", state["session_id"], item)
            continue
        rule_id, updated_record, log_msg = item
        if updated_record is not None:
            records[rule_id] = updated_record
            log_messages.append(log_msg)

    return {
        "parameter_records": records,
        "current_phase": "evaluating",
        "progress_log": log_messages or ["Baselines ready: using production descriptions from CSV"],
    }


def _is_structured(description: str) -> bool:
    return description.strip().startswith("METRIC_NAME:")


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
    elif mode == "format":
        preamble = (
            f"The following plain-text description defines the evaluation criterion for this rule.\n"
            f"Convert it to the required structured format without changing the meaning, scope, or criteria.\n"
            f"Do not add, remove, or alter any conditions — only reformat.\n\n"
            f"Original description:\n{record['current_description']}\n\n"
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
