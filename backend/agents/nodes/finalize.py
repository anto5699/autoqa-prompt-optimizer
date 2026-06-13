import logging
from datetime import datetime, timezone

from agents.state import OptimizationState
from utils.session_store import session_store

logger = logging.getLogger(__name__)


async def finalize(state: OptimizationState) -> dict:
    logger.info("session=%s phase=finalizing", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "complete"})

    records = dict(state["parameter_records"])
    below_target = set(state["parameters_below_target"])

    for rule_id, record in records.items():
        if rule_id in below_target:
            records[rule_id] = {**record, "status": "max_iterations_reached"}
        else:
            records[rule_id] = {**record, "status": "converged"}

    total = len(records)
    meeting = [rid for rid, r in records.items() if r["status"] == "converged"]
    not_meeting = [rid for rid, r in records.items() if r["status"] == "max_iterations_reached"]
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

        parameters_report[rule_id] = {
            "status": record["status"],
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
            "optimization_notes": record.get("optimization_notes"),
            "iteration_history": record["iteration_history"] if converged else [
                {"iteration": h["iteration"], "accuracy": h["accuracy"]}
                for h in record["iteration_history"]
            ],
            "rca_findings": record.get("rca_findings"),
            "regression_warning": _build_regression_warning(record, initial_acc, final_acc) if regressed else None,
            "recommendations": _build_recommendations(record),
            "conversation_results": conversation_results,
        }

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
    if record["status"] == "converged" or not record.get("rca_findings"):
        return []
    recs = [
        "Review the RCA findings and manually refine the rule description.",
        "Consider whether this criterion is automatable from transcript evidence alone.",
    ]
    if record["false_positives"] > record["false_negatives"] * 2:
        recs.insert(0, "High false-positive rate — tighten specificity in PASS_CRITERIA.")
    elif record["false_negatives"] > record["false_positives"] * 2:
        recs.insert(0, "High false-negative rate — broaden or clarify the success criteria.")
    return recs
