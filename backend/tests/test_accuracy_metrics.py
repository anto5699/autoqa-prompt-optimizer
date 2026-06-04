import pytest

from utils.accuracy_metrics import compute_metrics


def gt_map(entries: dict) -> dict:
    """Build ground_truth_map with a single rule_id='r1'."""
    return {conv_id: {"r1": gt} for conv_id, gt in entries.items()}


# ── basic correctness ───────────────────────────────────────────────────────────

def test_perfect_accuracy():
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"}
    gt = gt_map({"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"})
    result = compute_metrics(preds, gt, "r1")
    assert result["accuracy"] == 1.0
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0
    assert result["tp"] == 2
    assert result["tn"] == 2
    assert result["fp"] == 0
    assert result["fn"] == 0


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
    assert result["tp"] == 1   # c1
    assert result["tn"] == 1   # c4
    assert result["fp"] == 1   # c3
    assert result["fn"] == 1   # c2
    assert result["accuracy"] == pytest.approx(0.5)


# ── NA exclusion ─────────────────────────────────────────────────────────────────

def test_na_ground_truths_excluded():
    preds = {"c1": "Yes", "c2": "Yes"}
    gt = gt_map({"c1": "Yes", "c2": "NA"})
    result = compute_metrics(preds, gt, "r1")
    # Only c1 counts
    assert result["tp"] == 1
    assert result["not_applicable_count"] == 1
    assert result["accuracy"] == 1.0


def test_all_na_returns_zeros():
    preds = {"c1": "Yes"}
    gt = gt_map({"c1": "NA"})
    result = compute_metrics(preds, gt, "r1")
    assert result["accuracy"] == 0.0
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0
    assert result["not_applicable_count"] == 1


def test_na_excluded_from_denominator():
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes"}
    gt = gt_map({"c1": "Yes", "c2": "No", "c3": "NA"})
    result = compute_metrics(preds, gt, "r1")
    assert result["not_applicable_count"] == 1
    assert result["tp"] + result["tn"] + result["fp"] + result["fn"] == 2


# ── zero-division safety ──────────────────────────────────────────────────────────

def test_zero_denominator_returns_zero_accuracy():
    result = compute_metrics({}, {}, "r1")
    assert result["accuracy"] == 0.0
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0


def test_zero_positive_predictions_precision_zero():
    preds = {"c1": "No", "c2": "No"}
    gt = gt_map({"c1": "Yes", "c2": "Yes"})
    result = compute_metrics(preds, gt, "r1")
    # TP=0, FP=0 → precision=0.0; FN=2 → recall=0.0
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0


# ── missing prediction defaults to "No" ───────────────────────────────────────────

def test_missing_prediction_defaults_to_no():
    preds = {}  # no predictions at all
    gt = gt_map({"c1": "Yes"})
    result = compute_metrics(preds, gt, "r1")
    assert result["fn"] == 1
    assert result["tp"] == 0
