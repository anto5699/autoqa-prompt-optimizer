import asyncio
import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import OptimizationState
from config import get_llm, settings
from utils.accuracy_metrics import wilson_interval
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = (
    "You are a QA expert writing plain-language summaries for call centre managers. "
    "Be concise, specific, and avoid technical jargon."
)
_MAX_DESCRIPTION_CHARS = 300


async def _generate_optimization_summary(
    rule_id: str, record: dict, initial_acc: float, final_acc: float, llm
) -> str:
    history = record.get("iteration_history", [])
    trajectory = " → ".join(f"{h['accuracy']:.0%}" for h in history) if history else "N/A"

    descriptions = [
        f"Iteration {h['iteration']}: {h['description'][:_MAX_DESCRIPTION_CHARS]}"
        for h in history
        if h.get("description")
    ]
    desc_section = (
        "How the rule wording changed across iterations:\n" + "\n".join(descriptions[:5]) + "\n\n"
        if descriptions else ""
    )

    original = (record.get("original_description") or "(none)").strip()

    is_dynamic = record.get("rule_type") == "dynamic"
    dynamic_note = (
        "\nNote: this is a dynamic metric with both a trigger condition (detects whether the scenario applies) "
        "and an answer condition (evaluates agent adherence). Both were optimized.\n"
        if is_dynamic else ""
    )
    prompt = (
        f"Parameter: {rule_id}\n"
        f"Initial accuracy: {initial_acc:.0%}  →  Final accuracy: {final_acc:.0%}\n"
        f"Accuracy across iterations: {trajectory}\n"
        f"{dynamic_note}\n"
        f"Original user description:\n{original}\n\n"
        f"{desc_section}"
        "Write a 2–3 sentence plain-English summary for a non-technical QA manager explaining:\n"
        "1. Why the evaluation rule was initially inaccurate\n"
        "2. What key changes were made across the optimization iterations to improve it\n\n"
        "Use this EXACT format (no markdown, no asterisks, no bullet points, no jargon):\n\n"
        "Why it was initially inaccurate: <one sentence in plain everyday language>\n\n"
        "What was improved: <one or two sentences describing the key changes>\n\n"
        "Do not say 'false positive', 'false negative', 'LLM', 'model', 'description', "
        "or 'criterion'. Say 'the evaluation rule' and 'the wording' instead."
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SUMMARY_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()


async def _generate_failure_summary(
    rule_id: str, record: dict, final_acc: float, target_acc: float, llm
) -> str:
    history = record.get("iteration_history", [])
    trajectory = " → ".join(f"{h['accuracy']:.0%}" for h in history) if history else "N/A"
    rca = (record.get("rca_findings") or "(no root cause analysis available)").strip()

    prompt = (
        f"Parameter: {rule_id}\n"
        f"Target accuracy: {target_acc:.0%}  |  Final accuracy: {final_acc:.0%}\n"
        f"Accuracy across {len(history)} iterations: {trajectory}\n\n"
        f"Root cause analysis:\n{rca}\n\n"
        "Write a plain-English report for a non-technical QA manager explaining:\n"
        "1. Why this evaluation rule could not reach the accuracy target\n"
        "2. Specific, actionable next steps a human should take to resolve this\n\n"
        "Use this EXACT format (no markdown, no asterisks, no jargon):\n\n"
        "Why it did not converge: <one sentence in plain everyday language>\n\n"
        "What was attempted: <one sentence on what the optimiser tried across iterations>\n\n"
        "Recommended next steps:\n"
        "• <specific action>\n"
        "• <specific action>\n"
        "• <third action if applicable>\n\n"
        "Do not say 'false positive', 'false negative', 'LLM', 'model', 'description', "
        "or 'criterion'. Say 'the evaluation rule' and 'the wording' instead."
    )

    response = await llm.ainvoke([
        SystemMessage(content=_SUMMARY_SYSTEM),
        HumanMessage(content=prompt),
    ])
    return response.content.strip()


async def finalize(state: OptimizationState) -> dict:
    logger.info("session=%s phase=finalizing", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "complete"})

    records = dict(state["parameter_records"])
    below_target = set(state["parameters_below_target"])

    for rule_id, record in records.items():
        # Only rules still actively optimizing at the cap become max_iterations_reached.
        # Preserve terminal statuses set upstream (converged / stalled / label_limited) so their
        # stop reason survives into the report.
        if rule_id in below_target or record.get("status") == "optimizing":
            records[rule_id] = {
                **record,
                "status": "max_iterations_reached",
                "stop_reason": record.get("stop_reason") or "max_iterations_reached",
            }
        elif record.get("status") == "converged" and not record.get("stop_reason"):
            records[rule_id] = {**record, "stop_reason": "converged"}

    total = len(records)
    meeting = [rid for rid, r in records.items() if r["status"] == "converged"]
    not_meeting = [rid for rid, r in records.items() if r["status"] != "converged"]
    overall_accuracy = (
        sum(r["current_accuracy"] for r in records.values()) / total if total else 0.0
    )
    overall_precision = (
        sum(r["current_precision"] for r in records.values()) / total if total else 0.0
    )
    overall_recall = (
        sum(r["current_recall"] for r in records.values()) / total if total else 0.0
    )

    gt_map = state["ground_truth_map"]

    pre_audit_results = state.get("pre_audit_results") or {}
    pre_audit_cases = state.get("pre_audit_cases") or {}
    gt_corrections_applied = state.get("gt_corrections_applied") or {}
    parameters_report: dict = {}
    for rule_id, record in records.items():
        converged = record["status"] == "converged"

        conversation_results = []
        for conv_id in sorted(record["current_predictions"].keys()):
            prediction = record["current_predictions"][conv_id]
            ground_truth = gt_map.get(conv_id, {}).get(rule_id, "NA")
            correct = None if ground_truth == "NA" else (prediction == ground_truth)
            conversation_results.append({
                "conversation_id": conv_id,
                "ground_truth": ground_truth,
                "prediction": prediction,
                "correct": correct,
            })

        initial_acc = record.get("initial_accuracy")
        if initial_acc is None:
            first = record["iteration_history"][0] if record["iteration_history"] else None
            initial_acc = first.get("accuracy") if first else None
        initial_desc = (
            record["iteration_history"][0].get("description", record["current_description"])
            if record["iteration_history"] else record["current_description"]
        )

        final_acc = record["current_accuracy"]
        regressed = initial_acc is not None and final_acc < initial_acc

        is_dynamic = record.get("rule_type") == "dynamic"
        pivot_approved = rule_id in (state.get("pivot_approved_rules") or [])
        pivot_info = None
        if pivot_approved:
            pivot_info = {
                "reason": record.get("alignment_audit") or "",
                "original_description": record.get("original_description") or "",
            }

        # --- Metric-quality signals (Change 4) ---
        _labels = [gt_map[c].get(rule_id) for c in gt_map if gt_map[c].get(rule_id) is not None]
        evaluable_n = sum(1 for v in _labels if v in ("Yes", "No"))  # Yes/No rows — fragile dimension
        low_confidence_metric = evaluable_n < settings.min_evaluable_n     # 5c
        # CI is on evaluable_n — the Yes/No denominator accuracy is actually computed over
        # (NA rows are excluded from accuracy), so the interval reflects the true evidence base;
        # using n_total understated uncertainty for high-NA metrics.
        accuracy_ci = wilson_interval(final_acc, evaluable_n)              # 5c
        _pa_cases = pre_audit_cases.get(rule_id) or []
        _flagged = len(_pa_cases)
        # Clamp to [0, 1]: flagged counts NA-flips too, so it can exceed evaluable_n on tiny
        # high-NA metrics; an unclamped score would go negative. 0.0 == maximally inconsistent.
        label_consistency_score = (                                        # 5b
            round(max(0.0, min(1.0, 1 - (_flagged / evaluable_n))), 4) if evaluable_n else None
        )
        # Change 3 — consensus confidence on proposed relabels (all 1.0 when single-judge)
        relabels_high_confidence = sum(1 for c in _pa_cases if c.get("confidence", 1.0) >= 0.999)
        relabels_contested = _flagged - relabels_high_confidence
        _confidences = record.get("current_confidences") or {}             # 5a (empty unless enabled)
        low_confidence_prediction_count = sum(
            1 for v in _confidences.values() if str(v).lower() == "low"
        ) if _confidences else None

        parameters_report[rule_id] = {
            "status": record["status"],
            "rule_type": record.get("rule_type", "answer"),
            "version": record.get("version", "v1"),
            "original_description": record.get("original_description") or "",
            "initial_prompt": initial_desc,
            "initial_accuracy": initial_acc,
            "final_accuracy": final_acc,
            "final_precision": record["current_precision"],
            "final_recall": record["current_recall"],
            "final_f1": record["current_f1"],
            "confusion_matrix": {
                "tp": record["true_positives"],
                "tn": record["true_negatives"],
                "fp": record["false_positives"],
                "fn": record["false_negatives"],
            },
            "not_applicable_count": record["not_applicable_count"],
            "final_prompt": record["current_description"],
            **({"final_trigger_prompt": record.get("trigger_description")} if is_dynamic else {}),
            "optimization_notes": record.get("optimization_notes"),
            "iteration_history": record["iteration_history"] if converged else [
                {"iteration": h["iteration"], "accuracy": h["accuracy"]}
                for h in record["iteration_history"]
            ],
            "rca_findings": record.get("rca_findings"),
            "regression_warning": _build_regression_warning(record, initial_acc, final_acc) if regressed else None,
            "recommendations": _build_recommendations(record),
            "conversation_results": conversation_results,
            "pivot_approved": pivot_approved,
            "pivot_info": pivot_info,
            "pre_audit_result": pre_audit_results.get(rule_id),
            "gt_audit_cases": pre_audit_cases.get(rule_id) or None,
            "gt_audit_flagged_count": (
                len(pre_audit_cases[rule_id]) if rule_id in pre_audit_cases else None
            ),
            "gt_corrections_applied": gt_corrections_applied.get(rule_id) or None,
            # --- New measurable signals ---
            "stop_reason": record.get("stop_reason"),
            "iterations_without_improvement": record.get("iterations_without_improvement"),
            "alignment_audit": record.get("alignment_audit"),  # surfaced for label_limited too
            "na_divergence": record.get("na_divergence"),
            "label_consistency_score": label_consistency_score,
            "low_confidence_metric": low_confidence_metric,
            "evaluable_n": evaluable_n,
            "accuracy_ci": accuracy_ci,
            "low_confidence_prediction_count": low_confidence_prediction_count,
            "relabels_high_confidence": relabels_high_confidence,
            "relabels_contested": relabels_contested,
        }

    # Generate plain-language report summaries for every parameter in parallel
    llm_config = state.get("llm_config", {})
    llm = get_llm(
        model=llm_config.get("optimizer_model") or llm_config.get("model"),
        api_key=llm_config.get("optimizer_api_key") or llm_config.get("api_key"),
        base_url=llm_config.get("optimizer_base_url") or llm_config.get("base_url"),
        purpose="optimizer",
    )
    sem = asyncio.Semaphore(settings.max_concurrent_llm_calls)
    target_acc = state["accuracy_target"]

    async def _gen_summary(rule_id: str):
        record = records[rule_id]
        final_acc = record["current_accuracy"]
        async with sem:
            try:
                if record["status"] == "converged":
                    initial_acc = record.get("initial_accuracy") or final_acc
                    text = await _generate_optimization_summary(rule_id, record, initial_acc, final_acc, llm)
                else:
                    text = await _generate_failure_summary(rule_id, record, final_acc, target_acc, llm)
                return rule_id, text
            except Exception as exc:
                logger.warning("session=%s rule_id=%s report_summary failed: %s", state["session_id"], rule_id, exc)
                return rule_id, None

    session_store.update(state["session_id"], {"current_phase": "generating_report"})
    summaries = await asyncio.gather(*[_gen_summary(rid) for rid in records])
    for rule_id, summary in summaries:
        if summary:
            parameters_report[rule_id]["report_summary"] = summary

    models_used = (session_store.get(state["session_id"]) or {}).get("models_used", {})

    final_report = {
        "session_id": state["session_id"],
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "summary": {
            "total_parameters": total,
            "parameters_meeting_target": len(meeting),
            "parameters_below_target": len(not_meeting),
            "overall_accuracy": overall_accuracy,
            "overall_precision": overall_precision,
            "overall_recall": overall_recall,
            "total_iterations": state["current_iteration"],
            "total_conversations": len(state["conversations"]),
            "accuracy_target": state["accuracy_target"],
            "models_used": models_used,
        },
        "parameters": parameters_report,
    }

    logger.info(
        "session=%s finalized: %d/%d rules converged",
        state["session_id"], len(meeting), total,
    )

    return {
        "parameter_records": records,
        "final_report": final_report,
        "optimization_complete": True,
        "current_phase": "complete",
        "progress_log": [
            f"Optimization complete: {len(meeting)}/{total} rules met the accuracy target"
        ],
    }


def _build_regression_warning(record: dict, initial_accuracy: float, final_accuracy: float) -> dict:
    delta = final_accuracy - initial_accuracy
    return {
        "message": (
            f"Final accuracy ({final_accuracy:.1%}) is lower than initial accuracy "
            f"({initial_accuracy:.1%}) — delta {delta:+.1%}."
        ),
        "root_cause": record.get("rca_findings") or "RCA not available for this rule.",
        "next_steps": [
            "Review iteration_history to identify which optimization step caused the drop.",
            "Inspect false positive and false negative cases in conversation_results.",
            "Rewrite the rule description using the structured format with explicit PASS_CRITERIA "
            "and FAIL EXAMPLES derived from the failing cases.",
            "Verify whether the criterion is deterministically evaluable from transcript text alone "
            "— if subjective judgment is required, the rule may need human review.",
        ],
    }


def _build_recommendations(record: dict) -> list[str]:
    if record["status"] == "converged":
        return []
    # Change 2 — label inconsistency: relabelling, not description rewriting, is the fix.
    if record.get("status") == "label_limited":
        return [
            "Ground-truth labels contradict the rule definition (LABELLING_INCONSISTENCY) — "
            "relabel the inconsistent conversations via the GT-audit flow. Do NOT keep rewriting "
            "the description; no wording can satisfy inconsistent labels.",
            "Decide the intended standard for this metric and re-label consistently to it.",
        ]
    recs: list[str] = []
    # Change 1 — stalled: make the no-progress diagnosis explicit.
    if record.get("status") == "stalled":
        recs.append(
            "Optimization made no progress after a GT alignment audit — the ceiling is likely the "
            "labels or an under-specified definition, not the wording. Review label quality first."
        )
    if not record.get("rca_findings"):
        return recs
    recs += [
        "Review the RCA findings and manually refine the rule description.",
        "Consider whether this criterion is automatable from transcript evidence alone.",
    ]
    if record["false_positives"] > record["false_negatives"] * 2:
        recs.insert(0, "High false-positive rate — tighten specificity in PASS_CRITERIA.")
    elif record["false_negatives"] > record["false_positives"] * 2:
        recs.insert(0, "High false-negative rate — broaden or clarify the success criteria.")
    return recs
