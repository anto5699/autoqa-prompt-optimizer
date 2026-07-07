import asyncio
import logging
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import ClarifyingQuestion, OptimizationState
from config import get_llm, settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_MAX_SAMPLES = 5
_MAX_TRANSCRIPT_MESSAGES = 10

_SYSTEM = (
    "You are a QA evaluation expert. Analyse whether a rule description is aligned with how ground "
    "truth labels were actually assigned in the provided conversation data.\n\n"
    "Your task: compare what the description claims to evaluate vs. what actually distinguishes the "
    "'Yes' (Adhered) examples from the 'No' (Not Adhered) examples in the data.\n\n"
    "Classify the gap type:\n"
    "  DESCRIPTION_MISMATCH: The description evaluates criterion A but the GT data rewards criterion B. "
    "The distinction between the Yes and No examples does not match what the description asks to evaluate.\n"
    "  NO_GAP: The description accurately captures what the GT labels reward. The Yes/No distinction "
    "matches the description's criterion.\n"
    "  LABELLING_INCONSISTENCY: Near-identical or equivalent conversations receive opposite GT labels. "
    "The data itself is inconsistent — the description is not the problem.\n\n"
    "Non-hallucination constraint: Only report patterns directly evidenced by the provided examples. "
    "Do not speculate about patterns not present in the data.\n"
    "Use plain English — no markdown, no asterisks, no jargon."
)


async def pre_flight_gt_audit(state: OptimizationState) -> dict:
    """Holistic GT alignment audit for ALL rules, runs once after csv_ingestion."""
    session_id = state["session_id"]
    rules = state["rules"]
    ground_truth_map = state["ground_truth_map"]
    conversations_by_id = {c["conversation_id"]: c for c in state["conversations"]}

    session_store.update(session_id, {"current_phase": "analyzing_failures"})
    session_store.append_log(
        session_id,
        f"Pre-flight GT audit: checking {len(rules)} rule(s) for description-GT alignment…",
    )

    llm_config = state.get("llm_config", {})
    llm = get_llm(
        model=llm_config.get("optimizer_model") or llm_config.get("model"),
        api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
        base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
        purpose="optimizer",
    )
    session_store.append_trace(session_id, {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "node": "pre_flight_gt_audit", "model": llm.model_name, "event": "start",
        "details": {"rules": len(rules)},
    })

    sem = asyncio.Semaphore(settings.max_concurrent_llm_calls)
    existing_pivot_asked = set(state.get("pivot_asked_rule_ids") or [])

    async def _audit_rule(rule: dict) -> tuple[str, str | None]:
        rule_id = rule["rule_id"]
        yes_cases = _sample_gt_cases(rule_id, "Yes", ground_truth_map, conversations_by_id)
        no_cases = _sample_gt_cases(rule_id, "No", ground_truth_map, conversations_by_id)

        if len(yes_cases) < 2 or len(no_cases) < 2:
            logger.info(
                "session=%s rule_id=%s pre-flight audit skipped (insufficient GT samples: %d yes, %d no)",
                session_id, rule_id, len(yes_cases), len(no_cases),
            )
            return rule_id, None

        async with sem:
            findings = await _run_audit(rule_id, rule, yes_cases, no_cases, llm)

        gap = _extract_gap_type(findings)
        session_store.append_log(session_id, f"  Pre-flight audit: {rule_id} — {gap}")
        return rule_id, findings

    audit_results = await asyncio.gather(*[_audit_rule(rule) for rule in rules])

    pre_audit_results: dict[str, str] = {}
    pivot_questions: list[ClarifyingQuestion] = []
    newly_pivot_asked: list[str] = []

    for rule_id, findings in audit_results:
        if findings is None:
            continue
        pre_audit_results[rule_id] = findings

        if "DESCRIPTION_MISMATCH" in findings and rule_id not in existing_pivot_asked:
            display_name = rule_id.replace("__answer", "").replace("__trigger", "")
            pivot_questions.append(ClarifyingQuestion(
                question_id=str(uuid.uuid4()),
                parameter_name=rule_id,
                question_text=(
                    f"Pre-flight GT audit found a logic mismatch for '{display_name}'.\n\n"
                    f"{findings}\n\n"
                    f"Would you like to rewrite the description from scratch based on what your GT data "
                    f"actually rewards? If yes, optimization will start with the correct logic from "
                    f"the very first iteration."
                ),
                rationale=(
                    "Pre-flight GT audit found DESCRIPTION_MISMATCH — description logic contradicts "
                    "ground truth before optimization begins."
                ),
                question_type="pivot",
            ))
            newly_pivot_asked.append(rule_id)

    mismatch_count = sum(1 for f in pre_audit_results.values() if "DESCRIPTION_MISMATCH" in f)
    logger.info(
        "session=%s pre-flight GT audit: %d rule(s) audited, %d mismatch(es)",
        session_id, len(pre_audit_results), mismatch_count,
    )

    return {
        "pre_audit_results": pre_audit_results,
        "clarifying_questions": pivot_questions,
        "pivot_asked_rule_ids": list(existing_pivot_asked | set(newly_pivot_asked)),
        "progress_log": [
            f"Pre-flight GT audit: {len(pre_audit_results)} rule(s) checked, "
            f"{mismatch_count} description mismatch(es) found"
        ],
    }


def _sample_gt_cases(
    rule_id: str,
    label: str,
    ground_truth_map: dict,
    conversations_by_id: dict,
) -> list[dict]:
    cases = []
    for conv_id, gt_by_rule in ground_truth_map.items():
        if gt_by_rule.get(rule_id) == label:
            conv = conversations_by_id.get(conv_id, {})
            cases.append({"conversation_id": conv_id, "transcript": conv.get("transcript", [])})
            if len(cases) >= _MAX_SAMPLES:
                break
    return cases


def _format_transcript(messages: list) -> str:
    lines = []
    for m in messages[:_MAX_TRANSCRIPT_MESSAGES]:
        speaker = m.get("speaker", "unknown").title()
        lines.append(f"  {speaker}: {m.get('msg', '')}")
    if len(messages) > _MAX_TRANSCRIPT_MESSAGES:
        lines.append(f"  [...{len(messages) - _MAX_TRANSCRIPT_MESSAGES} more messages]")
    return "\n".join(lines) if lines else "  (no transcript)"


def _extract_gap_type(findings: str) -> str:
    for line in findings.split("\n"):
        stripped = line.strip()
        if stripped.startswith("Gap type:"):
            return stripped[len("Gap type:"):].strip()
    return "UNKNOWN"


async def _run_audit(rule_id: str, rule: dict, yes_cases: list, no_cases: list, llm) -> str:
    yes_text = "\n\n".join(
        f"[Y{i + 1}] Conversation {c['conversation_id']}:\n{_format_transcript(c['transcript'])}"
        for i, c in enumerate(yes_cases)
    ) or "No Yes-labeled cases available."

    no_text = "\n\n".join(
        f"[N{i + 1}] Conversation {c['conversation_id']}:\n{_format_transcript(c['transcript'])}"
        for i, c in enumerate(no_cases)
    ) or "No No-labeled cases available."

    prompt = (
        f"Rule ID: {rule_id}\n"
        f"Rule type: {rule.get('rule_type', 'answer')} | Speaker: {rule.get('speaker', 'agent')} | "
        f"Evaluation type: {rule.get('evaluation_type', 'entire')}\n\n"
        f"Description:\n{rule.get('description', '')}\n\n"
        f"YES examples — conversations where the agent ADHERED (labelled 'Yes' in ground truth):\n"
        f"{yes_text}\n\n"
        f"NO examples — conversations where the agent did NOT ADHERE (labelled 'No' in ground truth):\n"
        f"{no_text}\n\n"
        "Based on these examples:\n"
        "1. What behaviour or criterion actually distinguishes the 'Yes' from 'No' conversations?\n"
        "2. Does this match what the description says should be evaluated?\n"
        "3. If there is a mismatch, describe it specifically.\n\n"
        "Respond using this EXACT format:\n\n"
        "Gap type: <LABELLING_INCONSISTENCY | NO_GAP | DESCRIPTION_MISMATCH>\n\n"
        "What the description evaluates: <one sentence>\n"
        "What GT data rewards: <one sentence based on what distinguishes Yes from No examples>\n\n"
        "Alignment gaps:\n"
        "• <specific gap, or None.>\n\n"
        "Revised optimization strategy:\n"
        "<One concrete instruction if DESCRIPTION_MISMATCH, or 'No changes needed.' if NO_GAP or LABELLING_INCONSISTENCY>"
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()
