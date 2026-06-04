import logging

from agents.state import OptimizationState
from utils.accuracy_metrics import compute_metrics
from utils.session_store import session_store

logger = logging.getLogger(__name__)


async def benchmarking(state: OptimizationState) -> dict:
    logger.info(
        "session=%s phase=benchmarking iteration=%d",
        state["session_id"], state["current_iteration"],
    )
    session_store.update(state["session_id"], {"current_phase": "benchmarking"})

    records = dict(state["parameter_records"])
    ground_truth_map = state["ground_truth_map"]
    accuracy_target = state["accuracy_target"]
    current_iteration = state["current_iteration"]

    meeting_target: list[str] = []
    below_target: list[str] = []
    log_lines: list[str] = []

    for rule_id, record in records.items():
        # Converged rules are locked — never re-evaluated or re-routed
        if record.get("status") == "converged":
            meeting_target.append(rule_id)
            log_lines.append(
                f"Iteration {current_iteration} | {rule_id}: "
                f"converged (locked) accuracy={record['current_accuracy']:.2%}"
            )
            continue

        metrics = compute_metrics(record["current_predictions"], ground_truth_map, rule_id)
        new_accuracy = metrics["accuracy"]

        # First pass: seed regression tracking
        if record.get("initial_accuracy") is None:
            initial_accuracy = new_accuracy
            best_accuracy = new_accuracy
            best_description = record["current_description"]
        else:
            initial_accuracy = record["initial_accuracy"]
            best_accuracy = record["best_accuracy"] if record["best_accuracy"] is not None else record["initial_accuracy"]
            best_description = record["best_description"] if record["best_description"] is not None else record["current_description"]

        # Regression guard: revert description if this iteration was worse than best
        if new_accuracy < best_accuracy and record.get("initial_accuracy") is not None:
            current_description = best_description
            logger.info(
                "session=%s rule_id=%s regression detected (%.2f < %.2f) — reverting description",
                state["session_id"], rule_id, new_accuracy, best_accuracy,
            )
        else:
            current_description = record["current_description"]
            if new_accuracy >= best_accuracy:
                best_accuracy = new_accuracy
                best_description = record["current_description"]

        history_entry = {
            "iteration": current_iteration,
            "description": record["current_description"],
            "accuracy": new_accuracy,
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
        }

        updated_record = {
            **record,
            "current_description": current_description,
            "current_accuracy": new_accuracy,
            "current_precision": metrics["precision"],
            "current_recall": metrics["recall"],
            "current_f1": metrics["f1"],
            "true_positives": metrics["tp"],
            "false_positives": metrics["fp"],
            "true_negatives": metrics["tn"],
            "false_negatives": metrics["fn"],
            "not_applicable_count": metrics["not_applicable_count"],
            "initial_accuracy": initial_accuracy,
            "best_accuracy": best_accuracy,
            "best_description": best_description,
            "iteration_history": [*record["iteration_history"], history_entry],
        }

        if new_accuracy >= accuracy_target:
            updated_record["status"] = "converged"
            meeting_target.append(rule_id)
        else:
            updated_record["status"] = "optimizing"
            below_target.append(rule_id)

        records[rule_id] = updated_record
        log_lines.append(
            f"Iteration {current_iteration} | {rule_id}: "
            f"accuracy={new_accuracy:.2%} "
            f"(TP={metrics['tp']} TN={metrics['tn']} FP={metrics['fp']} FN={metrics['fn']})"
        )
        logger.info(
            "session=%s rule_id=%s iteration=%d accuracy=%.4f",
            state["session_id"], rule_id, current_iteration, new_accuracy,
        )

    return {
        "parameter_records": records,
        "parameters_meeting_target": meeting_target,
        "parameters_below_target": below_target,
        "current_phase": "benchmarking",
        "progress_log": log_lines,
    }
