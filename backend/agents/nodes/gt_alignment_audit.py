import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from agents.nodes.benchmarking import _iters_without_improvement
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


def _no_progress(record: dict) -> bool:
    """A rule that is not making progress and should be audited.

    Two shapes count: (1) tight-flat stagnation (`_is_stagnant`), and (2) — when
    `audit_on_no_improvement` is set — oscillation, where the raw accuracy is not tight-flat but
    `best` has not been beaten for `stagnation_window` iterations. Without (2), an oscillating-down
    rule never gets audited and so can never reach the stalled / label_limited halts (both gated on
    a prior audit). Requires at least `stagnation_window` history entries for either shape.
    """
    if _is_stagnant(record):
        return True
    if not settings.audit_on_no_improvement:
        return False
    history = record.get("iteration_history", [])
    if len(history) < settings.stagnation_window:
        return False
    return _iters_without_improvement(history, settings.min_improvement_delta) >= settings.stagnation_window


async def gt_alignment_audit(state: OptimizationState) -> dict:
    session_id = state["session_id"]
    iteration = state["current_iteration"]
    below_target = state["parameters_below_target"]
    records = dict(state["parameter_records"])
    ground_truth_map = state["ground_truth_map"]
    conversations_by_id = {c["conversation_id"]: c for c in state["conversations"]}

    stagnant_rules = [
        rule_id for rule_id in below_target
        if _no_progress(records[rule_id])
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
        is_dynamic = record.get("rule_type") == "dynamic"
        keep_na_cases = is_dynamic or record.get("version") == "v2"
        correct_cases = _collect_correct_cases(rule_id, predictions, ground_truth_map, conversations_by_id)
        error_cases = _collect_error_cases(rule_id, predictions, ground_truth_map, conversations_by_id, keep_na_cases=keep_na_cases)

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
    keep_na_cases: bool = False,
) -> list[dict]:
    """Collect misclassified cases as evidence for the alignment audit.

    For rules that can legitimately produce NA — V1 dynamic (By Question) rules, and V2
    unified rules whose NA comes from an unmet CONDITION or a satisfied EXCEPTION — GT=NA
    rows are NOT skipped: a prediction that disagrees with GT=NA is a gate over-fire, and
    GT=Yes/No with a NA prediction is a missed/over-strict gate — both are genuine gate-side
    failures the audit must be able to see, not just answer-side (Yes vs No) misclassification.
    Static (non-conditional) rules keep the original behaviour (NA is genuinely inapplicable,
    there is no gate condition to recover).
    """
    cases = []
    for conv_id, gt_by_rule in ground_truth_map.items():
        gt = gt_by_rule.get(rule_id)
        if gt is None:
            continue
        if gt == "NA" and not keep_na_cases:
            continue
        pred = predictions.get(conv_id, "No")
        if pred == gt:
            continue
        conv = conversations_by_id.get(conv_id, {})
        if gt == "NA":
            error_type = "trigger_overfire"
        elif pred == "NA":
            error_type = "missed_trigger"
        elif pred == "Yes":
            error_type = "false_positive"
        elif pred == "No":
            error_type = "false_negative"
        else:
            continue
        cases.append({
            "ground_truth": gt,
            "prediction": pred,
            "error_type": error_type,
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
    is_dynamic = record.get("rule_type") == "dynamic"
    is_v2 = record.get("version") == "v2"

    if is_dynamic:
        trigger_desc = record.get("trigger_description") or "(none)"
        description_section = (
            f"Trigger description (detects whether the scenario applies — speaker: "
            f"{record.get('trigger_speaker', 'customer')}):\n{trigger_desc}\n\n"
            f"Answer description (evaluates agent adherence when the scenario is present — "
            f"speaker: {record['speaker']}):\n{record['current_description']}\n\n"
        )
        attribution_ask = (
            "Identify whether the failure is in the trigger condition (failing to detect the scenario, "
            "OR firing when the scenario is absent — over-firing), the answer condition (misclassifying "
            "adherence when the scenario is present), or both. For trigger over-fire or missed-trigger "
            "cases, state clearly that the TRIGGER description — not the answer description — needs to "
            "change.\n\n"
        )
    elif is_v2:
        description_section = (
            f"V2 unified description (CONDITION / EXPECTED BEHAVIOR / PROHIBITED (optional) / "
            f"EXCEPTION sections embedded below — speaker: {record['speaker']}):\n"
            f"{record['current_description']}\n\n"
        )
        attribution_ask = (
            "Identify whether the failure is in the CONDITION/EXCEPTION gate (the rule fired when the "
            "CONDITION was not met, or failed to resolve NA when an EXCEPTION applied — these show up "
            "as GT=NA disagreements) or in EXPECTED BEHAVIOR/PROHIBITED (misjudging agent adherence once "
            "the gate is passed). For gate-side failures, state clearly that the CONDITION or EXCEPTION "
            "section — not EXPECTED BEHAVIOR — needs to change.\n\n"
        )
    else:
        description_section = f"Current description:\n{record['current_description']}\n\n"
        attribution_ask = ""

    correct_text = "\n\n".join(
        f"[C{i + 1}] GT={c['ground_truth']} (correct)\n"
        f"Transcript:\n{_format_transcript(c['transcript'])}"
        for i, c in enumerate(correct_cases)
    ) or "No correctly classified cases available."

    error_text = "\n\n".join(
        f"[E{i + 1}] GT={e['ground_truth']} | Predicted={e['prediction']}"
        + (f" | Type={e['error_type'].replace('_', ' ')}" if (is_dynamic or is_v2) and e.get("error_type") else "")
        + f"\nTranscript:\n{_format_transcript(e['transcript'])}"
        for i, e in enumerate(error_cases)
    ) or "No error cases available."

    prompt = (
        f"Rule ID: {rule_id}\n"
        f"Rule type: {record['rule_type']} | Speaker: {record['speaker']} | "
        f"Evaluation type: {record['evaluation_type']}\n\n"
        f"{description_section}"
        f"Accuracy trajectory: {trajectory}\n"
        f"This rule has been stagnant — multiple description rewrites have not improved accuracy.\n\n"
        f"Correctly classified examples — what the ground truth expects to pass or fail:\n{correct_text}\n\n"
        f"Persistently misclassified examples — cases that keep being evaluated wrongly:\n{error_text}\n\n"
        "Analyse the gap between what the description evaluates and what ground truth actually rewards.\n"
        f"{attribution_ask}"
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
        "'change the evaluation to require...' instead."
        + (" If the fix is on the trigger side, say 'rewrite the trigger description to...' instead."
           if is_dynamic else
           " If the fix is on the CONDITION/EXCEPTION gate, say 'rewrite the CONDITION/EXCEPTION "
           "section to...' instead." if is_v2 else "")
        + ">"
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()
