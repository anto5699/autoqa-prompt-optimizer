import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import OptimizationState
from config import get_llm
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert QA rule analyst. Analyse evaluation errors to identify root causes "
    "in the rule description that cause misclassification. Be specific and actionable."
)
_MAX_TRANSCRIPT_MESSAGES = 12


async def rca_analyzer(state: OptimizationState) -> dict:
    session_id = state["session_id"]
    iteration = state["current_iteration"]
    logger.info("session=%s phase=analyzing_failures iteration=%d", session_id, iteration)
    session_store.update(session_id, {"current_phase": "analyzing_failures"})
    session_store.append_log(session_id, f"Iteration {iteration}: analysing failures for {len(state['parameters_below_target'])} rule(s)…")

    llm_config = state.get("llm_config", {})
    llm = get_llm(
        model=llm_config.get("optimizer_model") or llm_config.get("model"),
        api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
        base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
        purpose="optimizer",
    )
    session_store.append_trace(session_id, {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "node": "rca_analyzer", "model": llm.model_name, "event": "start",
        "details": {"iteration": iteration, "rules_below_target": len(state["parameters_below_target"])},
    })

    records = dict(state["parameter_records"])
    ground_truth_map = state["ground_truth_map"]
    conversations_by_id = {c["conversation_id"]: c for c in state["conversations"]}
    below_target = state["parameters_below_target"]

    total_rules = len(below_target)
    session_store.update(session_id, {"node_progress": {"node": "analyzing_failures", "step": 0, "total": total_rules}})

    for idx, rule_id in enumerate(below_target):
        record = records[rule_id]
        session_store.append_log(session_id, f"  RCA: {rule_id}…")
        error_cases = _collect_error_cases(
            rule_id,
            record["current_predictions"],
            record.get("current_rationales", {}),
            ground_truth_map,
            conversations_by_id,
            version=record.get("version", "v1"),
        )
        findings = await _run_rca(rule_id, record, error_cases, session_id, llm)
        records[rule_id] = {**record, "rca_findings": findings}
        logger.info("session=%s rule_id=%s RCA complete", session_id, rule_id)
        session_store.set_node_progress(session_id, "analyzing_failures", idx + 1, total_rules)

    return {
        "parameter_records": records,
        "current_phase": "optimizing_prompts",
        "progress_log": [f"RCA complete for {len(below_target)} rule(s)"],
    }


def _collect_error_cases(
    rule_id: str,
    predictions: dict,
    rationales: dict,
    ground_truth_map: dict,
    conversations_by_id: dict,
    version: str = "v1",
) -> list[dict]:
    errors = []
    for conv_id, gt_by_rule in ground_truth_map.items():
        gt = gt_by_rule.get(rule_id)
        if gt == "NA" or gt is None:
            continue
        pred = predictions.get(conv_id, "No")
        if pred != gt:
            conv = conversations_by_id.get(conv_id, {})
            if version == "v1":
                if pred == "NA" and gt != "NA":
                    error_type = "missed_trigger"
                elif pred == "Yes" and gt != "Yes":
                    error_type = "false_positive"
                elif pred == "No" and gt != "No":
                    error_type = "false_negative"
                else:
                    continue
            else:  # v2
                if pred == "Yes" and gt != "Yes":
                    error_type = "false_positive"
                elif pred == "No" and gt != "No":
                    error_type = "false_negative"
                elif pred == "NA" and gt != "NA":
                    error_type = "false_na_prediction"
                else:
                    continue
            errors.append({
                "conversation_id": conv_id,
                "ground_truth": gt,
                "prediction": pred,
                "error_type": error_type,
                "transcript": conv.get("transcript", []),
                "rationale": rationales.get(conv_id, ""),
            })
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
    rule_id: str, record: dict, error_cases: list[dict], session_id: str, llm
) -> str:
    rule_type = record["rule_type"]
    version = record.get("version", "v1")

    if version == "v2":
        rule_desc_block = (
            f"Rule ID: {rule_id}\n"
            f"Speaker: {record.get('speaker')}\n"
            f"V2 Unified Criteria description:\n{record['current_description']}\n"
        )
        description_section = rule_desc_block + "\n"
        error_labels = {
            "false_positive": "Predicted YES (adhered) but ground truth is NO — agent did not satisfy EXPECTED BEHAVIOR",
            "false_negative": "Predicted NO (not adhered) but ground truth is YES — agent actually satisfied EXPECTED BEHAVIOR",
            "false_na_prediction": "Predicted NA but ground truth is YES or NO — CONDITION or EXCEPTION mis-triggered",
        }
        error_labels_str = "\n".join(f"{k}: {v}" for k, v in error_labels.items())
        ask = (
            "Frame fixes in terms of CONDITION (trigger accuracy), "
            "EXPECTED BEHAVIOR (completeness and clarity of required action), "
            "PROHIBITED (if over-triggering NO), and EXCEPTION (if over-triggering NA)."
        )
    else:
        error_labels_str = None  # set per rule_type below
        if rule_type == "trigger":
            error_labels_str = (
                "False positive = LLM said trigger fired (isQualified: true) but GT=No.\n"
                "False negative = LLM said trigger absent (isQualified: false) but GT=Yes."
            )
            ask = (
                "Identify what in the description causes misdetection: "
                "is it ambiguous phrasing, too broad, too narrow, or scope mismatch?"
            )
            description_section = f"Current description:\n{record['current_description']}\n\n"
        elif rule_type == "dynamic":
            error_labels_str = (
                "False positive = predicted Yes (adhered) but GT=No (not adhered).\n"
                "False negative = predicted No (not adhered) but GT=Yes (adhered).\n"
                "Missed trigger = predicted NA (scenario absent) but GT=Yes or GT=No (scenario was present)."
            )
            ask = (
                "Identify whether the failure is in the trigger condition (failing to detect the scenario), "
                "the answer condition (misclassifying adherence when scenario is present), or both. "
                "Specify which description needs changing."
            )
            trigger_desc = record.get("trigger_description") or "(none)"
            description_section = (
                f"Trigger description (detects whether the scenario applies — speaker: {record.get('trigger_speaker', 'customer')}):\n"
                f"{trigger_desc}\n\n"
                f"Answer description (evaluates agent adherence when scenario is present — speaker: {record['speaker']}):\n"
                f"{record['current_description']}\n\n"
            )
        else:
            error_labels_str = (
                "False positive = LLM said adhered but GT=No.\n"
                "False negative = LLM said not adhered but GT=Yes."
            )
            ask = (
                "Identify what in the description causes misclassification: "
                "vague criteria, missing specificity, implicit knowledge required, or scope mismatch?"
            )
            description_section = f"Current description:\n{record['current_description']}\n\n"

    cases_text = "\n\n".join(
        f"[{i+1}] Error type: {e['error_type']}\n"
        f"Ground truth: {e['ground_truth']} | Prediction: {e['prediction']}\n"
        f"Evaluator's stated reason: {e['rationale'] or '(none provided)'}\n"
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
        f"{description_section}"
        f"{trajectory_str}"
        f"Error classification:\n{error_labels_str}\n\n"
        f"Error cases ({len(error_cases)} shown):\n{cases_text}\n\n"
        "The evaluator's stated reason shows how the wording was interpreted. "
        "Treat it as evidence of the interpretation, not as a confirmed cause — "
        "cross-check it against the transcript.\n\n"
        f"{ask}\n\n"
        "Respond using this EXACT format (plain English, no markdown, no asterisks, no jargon):\n\n"
        "Root cause: <one sentence in plain English — what the evaluation rule is getting wrong>\n\n"
        "Why it's failing:\n"
        "• <specific pattern observed in the error cases above>\n"
        "• <second pattern, or omit if only one pattern>\n\n"
        "What to improve: <one sentence on the specific change the wording needs — "
        "where the error pattern is clear, name the exact criterion and state its replacement>\n\n"
        "Use everyday language. Do not use the terms 'false positive', 'false negative', 'LLM', "
        "'model', 'description', or 'criterion'. Instead say 'incorrectly marked as Yes', "
        "'incorrectly marked as No', 'the evaluation rule', 'the wording'."
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()
