import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import OptimizationState
from config import get_llm
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert QA rule analyst. Analyse evaluation errors to identify root causes "
    "in the rule description that cause misclassification. Be specific and actionable."
)
_MAX_ERROR_CASES = 10
_MAX_TRANSCRIPT_MESSAGES = 12


async def rca_analyzer(state: OptimizationState) -> dict:
    session_id = state["session_id"]
    iteration = state["current_iteration"]
    logger.info("session=%s phase=analyzing_failures iteration=%d", session_id, iteration)
    session_store.update(session_id, {"current_phase": "analyzing_failures"})
    session_store.append_log(session_id, f"Iteration {iteration}: analysing failures for {len(state['parameters_below_target'])} rule(s)…")

    records = dict(state["parameter_records"])
    ground_truth_map = state["ground_truth_map"]
    conversations_by_id = {c["conversation_id"]: c for c in state["conversations"]}
    below_target = state["parameters_below_target"]

    for rule_id in below_target:
        record = records[rule_id]
        session_store.append_log(session_id, f"  RCA: {rule_id}…")
        error_cases = _collect_error_cases(
            rule_id, record["current_predictions"], ground_truth_map, conversations_by_id
        )
        findings = await _run_rca(rule_id, record, error_cases, session_id)
        records[rule_id] = {**record, "rca_findings": findings}
        logger.info("session=%s rule_id=%s RCA complete", session_id, rule_id)

    return {
        "parameter_records": records,
        "current_phase": "optimizing_prompts",
        "progress_log": [f"RCA complete for {len(below_target)} rule(s)"],
    }


def _collect_error_cases(
    rule_id: str,
    predictions: dict,
    ground_truth_map: dict,
    conversations_by_id: dict,
) -> list[dict]:
    errors = []
    for conv_id, gt_by_rule in ground_truth_map.items():
        gt = gt_by_rule.get(rule_id)
        if gt == "NA" or gt is None:
            continue
        pred = predictions.get(conv_id, "No")
        if pred != gt:
            conv = conversations_by_id.get(conv_id, {})
            errors.append({
                "conversation_id": conv_id,
                "ground_truth": gt,
                "prediction": pred,
                "error_type": "false_positive" if pred == "Yes" else "false_negative",
                "transcript": conv.get("transcript", []),
            })
            if len(errors) >= _MAX_ERROR_CASES:
                break
    return errors


def _format_transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages[:_MAX_TRANSCRIPT_MESSAGES]:
        speaker = m.get("speaker", "unknown").title()
        text = m.get("msg", "")
        lines.append(f"  {speaker}: {text}")
    if len(messages) > _MAX_TRANSCRIPT_MESSAGES:
        lines.append(f"  [...{len(messages) - _MAX_TRANSCRIPT_MESSAGES} more messages]")
    return "\n".join(lines) if lines else "  (no transcript)"


async def _run_rca(
    rule_id: str, record: dict, error_cases: list[dict], session_id: str
) -> str:
    rule_type = record["rule_type"]

    if rule_type == "trigger":
        error_labels = (
            "False positive = LLM said trigger fired (isQualified: true) but GT=No.\n"
            "False negative = LLM said trigger absent (isQualified: false) but GT=Yes."
        )
        ask = (
            "Identify what in the description causes misdetection: "
            "is it ambiguous phrasing, too broad, too narrow, or scope mismatch?"
        )
    else:
        error_labels = (
            "False positive = LLM said adhered but GT=No.\n"
            "False negative = LLM said not adhered but GT=Yes."
        )
        ask = (
            "Identify what in the description causes misclassification: "
            "vague criteria, missing specificity, implicit knowledge required, or scope mismatch?"
        )

    cases_text = "\n\n".join(
        f"[{i+1}] Error type: {e['error_type']}\n"
        f"Ground truth: {e['ground_truth']} | Prediction: {e['prediction']}\n"
        f"Transcript:\n{_format_transcript(e['transcript'])}"
        for i, e in enumerate(error_cases)
    )

    history = record.get("iteration_history", [])
    trajectory_str = (
        "Accuracy trajectory: " + " → ".join(f"{h['accuracy']:.0%}" for h in history) + "\n\n"
        if history else ""
    )

    prompt = (
        f"Rule ID: {rule_id}\n"
        f"Rule type: {rule_type} | Speaker: {record['speaker']} | "
        f"Evaluation type: {record['evaluation_type']}\n\n"
        f"Current description:\n{record['current_description']}\n\n"
        f"{trajectory_str}"
        f"Error classification:\n{error_labels}\n\n"
        f"Error cases ({len(error_cases)} shown):\n{cases_text}\n\n"
        f"{ask}\n\n"
        "Provide a concise analysis (3–5 sentences) identifying the root cause(s) "
        "and what specifically needs to change in the description."
    )

    try:
        response = await get_llm().ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()
    except Exception as exc:
        logger.warning("session=%s rule_id=%s RCA LLM failed: %s", session_id, rule_id, type(exc).__name__)
        return f"RCA unavailable ({len(error_cases)} errors observed)."
