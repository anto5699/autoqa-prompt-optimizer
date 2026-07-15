import logging

from agents.state import LOCKED_STATUSES, OptimizationState
from config import settings
from utils.accuracy_metrics import compute_metrics
from utils.session_store import session_store

logger = logging.getLogger(__name__)


def _iters_without_improvement(history: list, min_delta: float) -> int:
    """Trailing iterations since accuracy last improved by >= min_delta. Pure function."""
    accs = [h["accuracy"] for h in history]
    if len(accs) <= 1:
        return 0
    best_so_far = accs[0]
    last_improve = 0
    for i in range(1, len(accs)):
        if accs[i] >= best_so_far + min_delta:
            best_so_far = accs[i]
            last_improve = i
    return (len(accs) - 1) - last_improve



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
        # Locked rules (converged / stalled / label_limited) are skipped — status panel shows why
        if record.get("status") in LOCKED_STATUSES:
            meeting_target.append(rule_id)
            continue

        metrics = compute_metrics(record["current_predictions"], ground_truth_map, rule_id)
        new_accuracy = metrics["accuracy"]
        is_dynamic = record.get("rule_type") == "dynamic" and record.get("version", "v1") == "v1"

        # NA-divergence detection (5d): predicted-NA rate vs ground-truth-NA rate. Symmetric and
        # neutral — a large gap in EITHER direction means predictions and labels disagree on scope;
        # the cause may be the trigger wording OR the NA labels. Warn-only; changes no control flow.
        # Both rates use the same denominator: conversations that HAVE a label for this rule.
        _labelled = [gt.get(rule_id) for gt in ground_truth_map.values() if gt.get(rule_id) is not None]
        _n_labelled = len(_labelled)
        _pred_na = sum(1 for cid in ground_truth_map
                       if ground_truth_map[cid].get(rule_id) is not None
                       and record["current_predictions"].get(cid) == "NA")
        _pred_na_rate = _pred_na / _n_labelled if _n_labelled else 0.0
        _gt_na_rate = sum(1 for v in _labelled if v == "NA") / _n_labelled if _n_labelled else 0.0
        _na_gap = _pred_na_rate - _gt_na_rate
        na_divergence = {
            "pred_na_rate": round(_pred_na_rate, 4),
            "gt_na_rate": round(_gt_na_rate, 4),
            "direction": ("pred_over_na" if _na_gap > 0.20
                          else "gt_over_na" if _na_gap < -0.20 else "aligned"),
        }
        if abs(_na_gap) > 0.20:
            _dir = ("predictions mark far MORE NA than the labels — audit trigger scope AND the NA labels"
                    if _na_gap > 0 else
                    "the labels mark far MORE NA than predictions — the GT may be over-using NA")
            session_store.append_log(
                state["session_id"],
                f"  ⚠ {rule_id}: NA divergence ({_pred_na_rate:.0%} predicted vs {_gt_na_rate:.0%} labelled) — {_dir}",
            )
            logger.warning(
                "session=%s rule_id=%s NA divergence: pred_na=%.2f gt_na=%.2f dir=%s",
                state["session_id"], rule_id, _pred_na_rate, _gt_na_rate, na_divergence["direction"],
            )

        # First pass: seed regression tracking
        if record.get("initial_accuracy") is None:
            initial_accuracy = new_accuracy
            best_accuracy = new_accuracy
            best_description = record["current_description"]
            best_trigger_description = record.get("trigger_description")
            best_predictions = dict(record.get("current_predictions") or {})
            best_rationales = dict(record.get("current_rationales") or {})
        else:
            initial_accuracy = record["initial_accuracy"]
            best_accuracy = record["best_accuracy"] if record["best_accuracy"] is not None else record["initial_accuracy"]
            best_description = record["best_description"] if record["best_description"] is not None else record["current_description"]
            best_trigger_description = record.get("best_trigger_description") or record.get("trigger_description")
            best_predictions = dict(record.get("best_predictions") or {})
            best_rationales = dict(record.get("best_rationales") or {})

        # Regression guard: revert description(s) and predictions if this iteration was worse than best
        if new_accuracy < best_accuracy and record.get("initial_accuracy") is not None:
            current_description = best_description
            current_trigger_description = best_trigger_description
            current_predictions = best_predictions
            current_rationales = best_rationales
            logger.info(
                "session=%s rule_id=%s regression detected (%.2f < %.2f) — reverting description and predictions",
                state["session_id"], rule_id, new_accuracy, best_accuracy,
            )
            session_store.append_log(
                state["session_id"],
                f"  ⚠ {rule_id}: regression ({new_accuracy:.0%} < {best_accuracy:.0%}) — reverted to best description",
            )
        else:
            current_description = record["current_description"]
            current_trigger_description = record.get("trigger_description")
            current_predictions = dict(record.get("current_predictions") or {})
            current_rationales = dict(record.get("current_rationales") or {})
            if new_accuracy >= best_accuracy:
                best_accuracy = new_accuracy
                best_description = record["current_description"]
                best_predictions = current_predictions
                best_rationales = current_rationales
                if is_dynamic:
                    best_trigger_description = record.get("trigger_description")

        history_entry = {
            "iteration": current_iteration,
            "description": record["current_description"],
            "accuracy": new_accuracy,
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
        }
        if is_dynamic:
            history_entry["trigger_description"] = record.get("trigger_description")

        updated_record = {
            **record,
            "current_description": current_description,
            "trigger_description": current_trigger_description,
            "current_predictions": current_predictions,
            "current_rationales": current_rationales,
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
            "best_trigger_description": best_trigger_description,
            "best_predictions": best_predictions,
            "best_rationales": best_rationales,
            "iteration_history": [*record["iteration_history"], history_entry],
            "na_divergence": na_divergence,
        }

        if new_accuracy >= accuracy_target:
            updated_record["status"] = "converged"
            updated_record["stop_reason"] = "converged"
            meeting_target.append(rule_id)
        else:
            # Change 1 — no-progress early-stop. Only after a GT alignment audit has run
            # (audit_iteration set) and the candidate accuracy has been flat for >= stall_patience
            # iterations. Never fires on an improving rule; only stops work, never alters accuracy.
            iters_flat = _iters_without_improvement(
                updated_record["iteration_history"], settings.min_improvement_delta
            )
            updated_record["iterations_without_improvement"] = iters_flat
            audited = record.get("audit_iteration") is not None
            if audited and iters_flat >= settings.stall_patience:
                updated_record["status"] = "stalled"
                updated_record["stop_reason"] = "stalled_no_progress"
                meeting_target.append(rule_id)  # not below_target → convergence_check can finalize
                session_store.append_log(
                    state["session_id"],
                    f"  ⏹ {rule_id}: no progress for {iters_flat} iteration(s) after GT audit "
                    f"(best {best_accuracy:.0%}) — stopping this metric",
                )
                logger.info(
                    "session=%s rule_id=%s stalled after %d flat iterations",
                    state["session_id"], rule_id, iters_flat,
                )
            else:
                updated_record["status"] = "optimizing"
                below_target.append(rule_id)

        records[rule_id] = updated_record
        log_lines.append(
            f"Iteration {current_iteration} | {rule_id}: "
            f"accuracy={new_accuracy:.2%} "
            f"(TP={metrics['tp']} TN={metrics['tn']} FP={metrics['fp']} FN={metrics['fn']} "
            f"NA✓={metrics['na_correct']} NA✗={metrics['na_wrong']})"
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
