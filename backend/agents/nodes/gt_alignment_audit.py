import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import OptimizationState
from config import get_llm, settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_MAX_CORRECT_CASES = 10
_MAX_ERROR_CASES = 10
_MAX_TRANSCRIPT_MESSAGES = 12


def _extract_gap_type(findings: str) -> str:
    """Read the 'Gap type:' line the audit prompt is required to emit first."""
    for line in (findings or "").split("\n"):
        stripped = line.strip()
        if stripped.startswith("Gap type:"):
            return stripped[len("Gap type:"):].strip()
    return "UNKNOWN"

_SYSTEM = (
    "You are a QA evaluation expert. Analyse whether a rule description is fundamentally "
    "misaligned with how ground truth labels were assigned.\n\n"
    "STEP 1 — Classify the gap type before writing anything else:\n"
    "  LABELLING_INCONSISTENCY: Near-identical or equivalent transcripts receive opposite "
    "GT labels. The description is not the problem — the labels are. Recommend human "
    "relabeling of the inconsistent cases. Do not suggest description changes.\n"
    "  NO_GAP: All provided cases are correctly classified. The description accurately "
    "captures what GT rewards. State this clearly and recommend no changes. Stagnation "
    "in accuracy does not imply a description gap.\n"
    "  DESCRIPTION_MISMATCH: The description requires behaviour X but GT rewards behaviour Y. "
    "Identify the specific mismatch (e.g., wrong speaker scope, wrong criterion, missing "
    "criterion). Recommend a concrete revised optimization strategy.\n\n"
    "STEP 2 — Write your output:\n"
    "  Start with: 'Gap type: LABELLING_INCONSISTENCY | NO_GAP | DESCRIPTION_MISMATCH'\n"
    "  Then: 'Alignment gaps:' bullet list (or 'None.' for NO_GAP)\n"
    "  Then: 'Revised optimization strategy:' single concrete instruction\n\n"
    "Non-hallucination constraint: Only report gaps directly evidenced by the provided cases. "
    "Do not speculate about patterns not present in the data. Do not invent additional "
    "problems beyond what the cases demonstrate.\n"
    "Use plain English — no markdown, no asterisks, no jargon."
)


def _is_stagnant(record: dict, min_entries: int | None = None) -> bool:
    window = min_entries if min_entries is not None else settings.stagnation_window
    history = record.get("iteration_history", [])
    if len(history) < window:
        return False
    recent = [h["accuracy"] for h in history[-window:]]
    return (max(recent) - min(recent)) < settings.stagnation_spread


async def gt_alignment_audit(state: OptimizationState) -> dict:
    session_id = state["session_id"]
    iteration = state["current_iteration"]
    below_target = state["parameters_below_target"]
    records = dict(state["parameter_records"])
    ground_truth_map = state["ground_truth_map"]
    conversations_by_id = {c["conversation_id"]: c for c in state["conversations"]}

    stagnant_rules = [
        rule_id for rule_id in below_target
        if _is_stagnant(records[rule_id])
        and _should_audit(records[rule_id], iteration)
    ]

    if not stagnant_rules:
        return {}

    session_store.update(session_id, {"current_phase": "analyzing_failures"})
    session_store.append_log(
        session_id,
        f"Iteration {iteration}: GT alignment audit for {len(stagnant_rules)} stagnant rule(s)…",
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
        "node": "gt_alignment_audit", "model": llm.model_name, "event": "start",
        "details": {"iteration": iteration, "stagnant_rules": len(stagnant_rules)},
    })

    total = len(stagnant_rules)
    session_store.update(session_id, {"node_progress": {"node": "analyzing_failures", "step": 0, "total": total}})

    halted: list[str] = []  # Change 2: rules the audit found label-limited

    for idx, rule_id in enumerate(stagnant_rules):
        record = records[rule_id]
        session_store.append_log(session_id, f"  GT audit: {rule_id}…")

        predictions = record["current_predictions"]
        correct_cases = _collect_correct_cases(rule_id, predictions, ground_truth_map, conversations_by_id)
        error_cases = _collect_error_cases(rule_id, predictions, ground_truth_map, conversations_by_id)

        findings = await _run_audit(rule_id, record, correct_cases, error_cases, llm)
        updated = {**record, "alignment_audit": findings, "audit_iteration": iteration}

        # Change 2 — make LABELLING_INCONSISTENCY actionable: halt the rule instead of
        # letting the loop keep rewriting a description against inconsistent labels.
        gap_type = _extract_gap_type(findings)
        if settings.enable_label_limited_halt and gap_type == "LABELLING_INCONSISTENCY":
            updated["status"] = "label_limited"
            updated["stop_reason"] = "label_inconsistency"
            halted.append(rule_id)
            session_store.append_log(
                session_id,
                f"  ⏹ {rule_id}: GT alignment audit found LABELLING_INCONSISTENCY — halting; "
                f"labels contradict the definition, relabelling is required (see recommendations)",
            )
            logger.info("session=%s rule_id=%s halted (label_limited)", session_id, rule_id)

        records[rule_id] = updated
        logger.info("session=%s rule_id=%s GT alignment audit complete (%s)", session_id, rule_id, gap_type)
        session_store.set_node_progress(session_id, "analyzing_failures", idx + 1, total)

    result: dict = {
        "parameter_records": records,
        "progress_log": [f"GT alignment audit complete for {len(stagnant_rules)} stagnant rule(s)"],
    }
    if halted:
        # Drop halted rules from the loop-driving list so convergence_check can finalize; keep
        # them tracked under meeting_target (the "not-optimizing" bucket).
        result["parameters_below_target"] = [r for r in below_target if r not in halted]
        result["parameters_meeting_target"] = [*state.get("parameters_meeting_target", []), *halted]
    return result


def _should_audit(record: dict, current_iteration: int) -> bool:
    last_audit = record.get("audit_iteration")
    if last_audit is None:
        return True
    return (current_iteration - last_audit) >= settings.min_iters_between_audits


def _collect_correct_cases(
    rule_id: str,
    predictions: dict,
    ground_truth_map: dict,
    conversations_by_id: dict,
) -> list[dict]:
    cases = []
    for conv_id, gt_by_rule in ground_truth_map.items():
        gt = gt_by_rule.get(rule_id)
        if gt is None or gt == "NA":
            continue
        pred = predictions.get(conv_id, "No")
        if pred == gt:
            conv = conversations_by_id.get(conv_id, {})
            cases.append({
                "ground_truth": gt,
                "transcript": conv.get("transcript", []),
            })
            if len(cases) >= _MAX_CORRECT_CASES:
                break
    return cases


def _collect_error_cases(
    rule_id: str,
    predictions: dict,
    ground_truth_map: dict,
    conversations_by_id: dict,
) -> list[dict]:
    cases = []
    for conv_id, gt_by_rule in ground_truth_map.items():
        gt = gt_by_rule.get(rule_id)
        if gt is None or gt == "NA":
            continue
        pred = predictions.get(conv_id, "No")
        if pred != gt:
            conv = conversations_by_id.get(conv_id, {})
            cases.append({
                "ground_truth": gt,
                "prediction": pred,
                "transcript": conv.get("transcript", []),
            })
            if len(cases) >= _MAX_ERROR_CASES:
                break
    return cases


def _format_transcript(messages: list) -> str:
    lines = []
    for m in messages[:_MAX_TRANSCRIPT_MESSAGES]:
        speaker = m.get("speaker", "unknown").title()
        text = m.get("msg", "")
        lines.append(f"  {speaker}: {text}")
    if len(messages) > _MAX_TRANSCRIPT_MESSAGES:
        lines.append(f"  [...{len(messages) - _MAX_TRANSCRIPT_MESSAGES} more messages]")
    return "\n".join(lines) if lines else "  (no transcript)"


async def _run_audit(
    rule_id: str,
    record: dict,
    correct_cases: list[dict],
    error_cases: list[dict],
    llm,
) -> str:
    history = record.get("iteration_history", [])
    trajectory = " → ".join(f"{h['accuracy']:.0%}" for h in history) if history else "no history"

    correct_text = "\n\n".join(
        f"[C{i + 1}] GT={c['ground_truth']} (correct)\n"
        f"Transcript:\n{_format_transcript(c['transcript'])}"
        for i, c in enumerate(correct_cases)
    ) or "No correctly classified cases available."

    error_text = "\n\n".join(
        f"[E{i + 1}] GT={e['ground_truth']} | Predicted={e['prediction']}\n"
        f"Transcript:\n{_format_transcript(e['transcript'])}"
        for i, e in enumerate(error_cases)
    ) or "No error cases available."

    prompt = (
        f"Rule ID: {rule_id}\n"
        f"Rule type: {record['rule_type']} | Speaker: {record['speaker']} | "
        f"Evaluation type: {record['evaluation_type']}\n\n"
        f"Current description:\n{record['current_description']}\n\n"
        f"Accuracy trajectory: {trajectory}\n"
        f"This rule has been stagnant — multiple description rewrites have not improved accuracy.\n\n"
        f"Correctly classified examples — what the ground truth expects to pass or fail:\n{correct_text}\n\n"
        f"Persistently misclassified examples — cases that keep being evaluated wrongly:\n{error_text}\n\n"
        "Analyse the gap between what the description evaluates and what ground truth actually rewards.\n"
        "Look for: (a) behaviours the GT marks as correct that the description cannot detect from "
        "transcript text alone, (b) cases where similar transcripts have opposite GT labels suggesting "
        "a labelling inconsistency, (c) implicit signals the description treats as absent that GT "
        "treats as present, (d) speaker scope mismatch — if the rule speaker is Agent but the criteria "
        "describe what the Customer says or does, flag that the criteria must be rewritten to evaluate "
        "Agent actions instead.\n\n"
        "Respond using this EXACT format:\n\n"
        "Gap type: <LABELLING_INCONSISTENCY | NO_GAP | DESCRIPTION_MISMATCH>\n\n"
        "Alignment gaps:\n"
        "• <specific gap 1>\n"
        "• <specific gap 2, or omit if only one>\n\n"
        "Revised optimization strategy:\n"
        "<One concrete instruction for how the description must change — describe the evaluation "
        "behaviour that needs to change in plain English. Do not use internal format terms like "
        "PASS_CRITERIA, PASS_LOGIC, or EXAMPLES — say 'rewrite the description to detect...' or "
        "'change the evaluation to require...' instead.>"
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()
