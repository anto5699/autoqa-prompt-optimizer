import pytest

from utils.accuracy_metrics import compute_metrics


def gt_map(entries: dict) -> dict:
    return {conv_id: {"r1": gt} for conv_id, gt in entries.items()}


# ── binary correctness ────────────────────────────────────────────────────────

def test_perfect_accuracy():
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"}
    gt = gt_map({"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"})
    result = compute_metrics(preds, gt, "r1")
    assert result["accuracy"] == 1.0
    assert result["tp"] == 2
    assert result["tn"] == 2
    assert result["fp"] == 0
    assert result["fn"] == 0
    assert result["na_correct"] == 0
    assert result["na_wrong"] == 0


def test_all_wrong():
    preds = {"c1": "No", "c2": "Yes"}
    gt = gt_map({"c1": "Yes", "c2": "No"})
    result = compute_metrics(preds, gt, "r1")
    assert result["accuracy"] == 0.0
    assert result["tp"] == 0
    assert result["tn"] == 0
    assert result["fp"] == 1
    assert result["fn"] == 1


def test_mixed_results():
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"}
    gt = gt_map({"c1": "Yes", "c2": "Yes", "c3": "No", "c4": "No"})
    result = compute_metrics(preds, gt, "r1")
    assert result["tp"] == 1    # c1
    assert result["tn"] == 1    # c4
    assert result["fp"] == 1    # c3
    assert result["fn"] == 1    # c2
    assert result["accuracy"] == pytest.approx(0.5)


# ── 3-class NA accuracy ────────────────────────────────────────────────────────

def test_na_gt_na_pred_counts_as_correct():
    preds = {"c1": "Yes", "c2": "NA"}
    gt = gt_map({"c1": "Yes", "c2": "NA"})
    result = compute_metrics(preds, gt, "r1")
    # c1=TP, c2=na_correct → 2/2 = 1.0
    assert result["accuracy"] == 1.0
    assert result["tp"] == 1
    assert result["na_correct"] == 1
    assert result["na_wrong"] == 0


def test_na_gt_with_wrong_pred_in_denominator():
    preds = {"c1": "Yes", "c2": "Yes"}   # c2 GT=NA but pred=Yes → wrong
    gt = gt_map({"c1": "Yes", "c2": "NA"})
    result = compute_metrics(preds, gt, "r1")
    # c1=TP (correct), c2=na_wrong (wrong) → 1/2 = 0.5
    assert result["accuracy"] == pytest.approx(0.5)
    assert result["tp"] == 1
    assert result["na_wrong"] == 1
    assert result["na_correct"] == 0


def test_wrong_na_pred_counted_and_in_denominator():
    # Trigger UNDER-fire: GT is in-scope (Yes/No) but the evaluator predicted NA.
    preds = {"c1": "NA", "c2": "NA", "c3": "Yes"}
    gt = gt_map({"c1": "Yes", "c2": "No", "c3": "Yes"})
    result = compute_metrics(preds, gt, "r1")
    # c1, c2 → wrong_na_pred (wrong); c3 → TP (correct). Accuracy = 1/3.
    assert result["wrong_na_pred"] == 2
    assert result["tp"] == 1
    assert result["accuracy"] == pytest.approx(1 / 3)
    # wrong_na_pred must be part of the denominator, not silently dropped
    assert result["na_correct"] == 0 and result["na_wrong"] == 0


def test_wrong_na_pred_key_always_present():
    # The field must be returned even when zero, so consumers never KeyError.
    result = compute_metrics({"c1": "Yes"}, gt_map({"c1": "Yes"}), "r1")
    assert "wrong_na_pred" in result
    assert result["wrong_na_pred"] == 0


def test_3class_mixed_accuracy():
    # c1: GT=Yes, pred=Yes → TP
    # c2: GT=No, pred=No → TN
    # c3: GT=NA, pred=NA → na_correct
    # c4: GT=NA, pred=Yes → na_wrong
    # Total correct = 3, total = 4 → 0.75
    preds = {"c1": "Yes", "c2": "No", "c3": "NA", "c4": "Yes"}
    gt = gt_map({"c1": "Yes", "c2": "No", "c3": "NA", "c4": "NA"})
    result = compute_metrics(preds, gt, "r1")
    assert result["tp"] == 1
    assert result["tn"] == 1
    assert result["na_correct"] == 1
    assert result["na_wrong"] == 1
    assert result["accuracy"] == pytest.approx(0.75)


def test_all_na_correct():
    preds = {"c1": "NA", "c2": "NA"}
    gt = gt_map({"c1": "NA", "c2": "NA"})
    result = compute_metrics(preds, gt, "r1")
    assert result["accuracy"] == 1.0
    assert result["na_correct"] == 2
    assert result["na_wrong"] == 0


def test_all_na_wrong():
    preds = {"c1": "Yes", "c2": "No"}
    gt = gt_map({"c1": "NA", "c2": "NA"})
    result = compute_metrics(preds, gt, "r1")
    assert result["accuracy"] == 0.0
    assert result["na_wrong"] == 2
    assert result["na_correct"] == 0


def test_not_applicable_count_backward_compat():
    preds = {"c1": "NA", "c2": "Yes"}
    gt = gt_map({"c1": "NA", "c2": "NA"})
    result = compute_metrics(preds, gt, "r1")
    assert result["not_applicable_count"] == 2   # na_correct + na_wrong


# ── zero-division safety ───────────────────────────────────────────────────────

def test_zero_denominator_returns_zero():
    result = compute_metrics({}, {}, "r1")
    assert result["accuracy"] == 0.0
    assert result["precision"] == 0.0


def test_none_gt_skipped():
    preds = {"c1": "Yes"}
    gt = {"c1": {"r1": None}}
    result = compute_metrics(preds, gt, "r1")
    assert result["accuracy"] == 0.0   # total=0 → 0.0


# ── binary precision/recall unchanged ─────────────────────────────────────────

def test_precision_recall_use_yes_no_only():
    # c1: TP, c2: FP, c3: na_correct — NA should not affect precision
    preds = {"c1": "Yes", "c2": "Yes", "c3": "NA"}
    gt = gt_map({"c1": "Yes", "c2": "No", "c3": "NA"})
    result = compute_metrics(preds, gt, "r1")
    assert result["precision"] == pytest.approx(0.5)   # tp=1 / (tp+fp=2)
    assert result["recall"] == pytest.approx(1.0)      # tp=1 / (tp+fn=1)


def test_missing_prediction_defaults_to_no():
    preds = {}
    gt = gt_map({"c1": "Yes"})
    result = compute_metrics(preds, gt, "r1")
    assert result["fn"] == 1
    assert result["tp"] == 0
