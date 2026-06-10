import asyncio
import pytest

from agents.nodes.benchmarking import benchmarking


def _record(description, predictions, *, initial_accuracy=None, best_accuracy=None,
            best_description=None, status="optimizing", current_accuracy=0.0):
    return {
        "rule_id": "r1",
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        "current_description": description,
        "iteration_history": [],
        "current_predictions": predictions,
        "current_accuracy": current_accuracy,
        "current_precision": 0.0,
        "current_recall": 0.0,
        "current_f1": 0.0,
        "true_positives": 0,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0,
        "not_applicable_count": 0,
        "rca_findings": None,
        "optimization_notes": None,
        "status": status,
        "initial_accuracy": initial_accuracy,
        "best_accuracy": best_accuracy,
        "best_description": best_description,
    }


def _state(records, gt_map, *, iteration=0, target=0.9):
    return {
        "session_id": "test",
        "parameter_records": records,
        "ground_truth_map": gt_map,
        "accuracy_target": target,
        "current_iteration": iteration,
        "parameters_meeting_target": [],
        "parameters_below_target": [],
        "progress_log": [],
    }


def test_initial_accuracy_recorded_on_first_pass():
    # 3 correct / 4 total = 75%
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"}
    gt = {
        "c1": {"r1": "Yes"}, "c2": {"r1": "No"},
        "c3": {"r1": "Yes"}, "c4": {"r1": "Yes"},  # c4 FN
    }
    record = _record("desc v1", preds, initial_accuracy=None)
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=0)))

    r = result["parameter_records"]["r1"]
    assert r["initial_accuracy"] == pytest.approx(0.75)
    assert r["best_accuracy"] == pytest.approx(0.75)
    assert r["best_description"] == "desc v1"


def test_regression_reverts_description():
    # initial best: 80% with "desc v1"
    # current eval: TP=1 TN=1 FP=2 FN=1 = 2/5 = 40% with "desc v2"
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No", "c5": "Yes"}
    gt = {
        "c1": {"r1": "Yes"},   # TP
        "c2": {"r1": "No"},    # TN
        "c3": {"r1": "No"},    # FP
        "c4": {"r1": "Yes"},   # FN
        "c5": {"r1": "No"},    # FP
    }
    record = _record(
        "desc v2", preds,
        initial_accuracy=0.80, best_accuracy=0.80, best_description="desc v1",
    )
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=1)))

    r = result["parameter_records"]["r1"]
    assert r["current_description"] == "desc v1"   # reverted to best
    assert r["best_accuracy"] == pytest.approx(0.80)  # best unchanged
    assert r["current_accuracy"] == pytest.approx(0.40)  # actual eval accuracy preserved
    assert "r1" in result["parameters_below_target"]


def test_improvement_updates_best():
    # initial best: 80% with "desc v1"
    # current eval: 4/4 = 100% with "desc v2"
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"}
    gt = {"c1": {"r1": "Yes"}, "c2": {"r1": "No"}, "c3": {"r1": "Yes"}, "c4": {"r1": "No"}}
    record = _record(
        "desc v2", preds,
        initial_accuracy=0.80, best_accuracy=0.80, best_description="desc v1",
    )
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=1, target=0.9)))

    r = result["parameter_records"]["r1"]
    assert r["best_accuracy"] == pytest.approx(1.0)
    assert r["best_description"] == "desc v2"
    assert r["current_description"] == "desc v2"
    assert "r1" in result["parameters_meeting_target"]


def test_converged_rule_locked_regardless_of_new_predictions():
    # Rule is converged with 90% accuracy. Predictions would compute 0% if re-evaluated.
    # Expect: status stays converged, accuracy stays 90%, description unchanged.
    preds = {"c1": "Yes"}  # Would be FP if re-evaluated against GT below
    gt = {"c1": {"r1": "No"}}
    record = _record(
        "desc v1", preds,
        initial_accuracy=0.90, best_accuracy=0.90, best_description="desc v1",
        status="converged", current_accuracy=0.90,
    )
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=1)))

    r = result["parameter_records"]["r1"]
    assert r["status"] == "converged"
    assert r["current_accuracy"] == pytest.approx(0.90)  # not re-computed
    assert r["current_description"] == "desc v1"
    assert "r1" in result["parameters_meeting_target"]
    assert "r1" not in result["parameters_below_target"]


def test_zero_best_accuracy_not_treated_as_none():
    """best_accuracy=0.0 must not be falsy-coerced to initial_accuracy."""
    # current eval also 0% (FN) — same as best, no regression should fire
    preds = {"c1": "No"}
    gt = {"c1": {"r1": "Yes"}}  # FN → 0% accuracy
    record = _record(
        "desc v2", preds,
        initial_accuracy=0.5, best_accuracy=0.0, best_description="desc v1",
    )
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=2)))
    r = result["parameter_records"]["r1"]
    # 0.0 is NOT a regression vs best of 0.0 — do not revert
    assert r["current_description"] == "desc v2"
    assert r["best_description"] == "desc v2"  # 0.0 == 0.0, so update best to current


# ── trigger-gating ────────────────────────────────────────────────────────────

def _trigger_record(predictions, *, status="optimizing", current_accuracy=0.0):
    return {
        "rule_id": "metric__trigger",
        "rule_type": "trigger",
        "speaker": "agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        "current_description": "trigger desc",
        "iteration_history": [],
        "current_predictions": predictions,
        "current_accuracy": current_accuracy,
        "current_precision": 0.0,
        "current_recall": 0.0,
        "current_f1": 0.0,
        "true_positives": 0,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0,
        "not_applicable_count": 0,
        "rca_findings": None,
        "optimization_notes": None,
        "status": status,
        "initial_accuracy": None,
        "best_accuracy": None,
        "best_description": None,
    }


def test_trigger_gating_overrides_answer_pred_to_na():
    # trigger pred=No for c3 → answer pred should be gated to "NA"
    # c3 GT is NA in answer rule (out-of-scope conversation)
    # Without gating: pred=Yes vs GT=NA → na_wrong
    # With gating: pred=NA vs GT=NA → na_correct
    trigger_preds = {"c1": "Yes", "c2": "Yes", "c3": "No"}
    answer_preds  = {"c1": "Yes", "c2": "No",  "c3": "Yes"}
    gt = {
        "c1": {"metric__trigger": "Yes", "metric__answer": "Yes"},
        "c2": {"metric__trigger": "Yes", "metric__answer": "No"},
        "c3": {"metric__trigger": "No",  "metric__answer": "NA"},
    }
    trigger_rec = _trigger_record(trigger_preds)
    answer_rec  = _record("answer desc", answer_preds, initial_accuracy=None)
    answer_rec["rule_id"] = "metric__answer"
    trigger_rec["rule_id"] = "metric__trigger"

    result = asyncio.run(benchmarking(_state(
        {"metric__trigger": trigger_rec, "metric__answer": answer_rec},
        gt, iteration=0, target=0.9
    )))

    r = result["parameter_records"]["metric__answer"]
    # c1=TP, c2=TN, c3=na_correct (gated) → 3/3 = 1.0
    assert r["current_accuracy"] == pytest.approx(1.0)


def test_non_answer_rule_not_gated():
    preds = {"c1": "Yes", "c2": "No"}
    gt = {"c1": {"r1": "Yes"}, "c2": {"r1": "No"}}
    record = _record("desc", preds, initial_accuracy=None)
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=0)))
    r = result["parameter_records"]["r1"]
    assert r["current_accuracy"] == pytest.approx(1.0)


def test_trigger_gating_without_matching_trigger_record():
    # __answer rule exists but no __trigger record → predictions unchanged
    answer_preds = {"c1": "Yes", "c2": "No"}
    gt = {
        "c1": {"metric__answer": "Yes"},
        "c2": {"metric__answer": "No"},
    }
    answer_rec = _record("answer desc", answer_preds, initial_accuracy=None)
    answer_rec["rule_id"] = "metric__answer"
    result = asyncio.run(benchmarking(_state({"metric__answer": answer_rec}, gt, iteration=0)))
    r = result["parameter_records"]["metric__answer"]
    assert r["current_accuracy"] == pytest.approx(1.0)
