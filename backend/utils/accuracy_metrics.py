import math
from typing import Dict, Optional


def wilson_interval(p: float, n: int, z: float = 1.96) -> Optional[Dict[str, float]]:
    """95% Wilson score interval for a proportion p over n trials. None if n == 0.

    Used for minimum-N gating (5c): a tiny n yields a very wide interval, which is exactly
    the "this accuracy is statistically fragile" signal we want to surface. Pure function.
    """
    if n <= 0:
        return None
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return {"low": round(max(0.0, centre - margin), 4), "high": round(min(1.0, centre + margin), 4)}


def compute_metrics(
    predictions: Dict[str, str],
    ground_truth_map: Dict[str, Dict[str, str]],
    rule_id: str,
) -> dict:
    """3-class accuracy: Yes / No / NA all count in denominator.

    na_correct = GT=NA and pred=NA → correct
    na_wrong   = GT=NA and pred=Yes/No → wrong
    Binary precision/recall/F1 use Yes/No only (NA predictions excluded).
    """
    tp = tn = fp = fn = na_correct = na_wrong = wrong_na_pred = 0

    for conv_id, gt_by_rule in ground_truth_map.items():
        gt = gt_by_rule.get(rule_id)
        pred = predictions.get(conv_id, "No")

        if gt is None:
            continue

        if gt == "NA":
            if pred == "NA":
                na_correct += 1
            else:
                na_wrong += 1
        elif pred == "NA":
            wrong_na_pred += 1
        elif gt == "Yes" and pred == "Yes":
            tp += 1
        elif gt == "No" and pred == "No":
            tn += 1
        elif gt == "No" and pred == "Yes":
            fp += 1
        elif gt == "Yes" and pred == "No":
            fn += 1

    total = tp + tn + fp + fn + na_correct + na_wrong + wrong_na_pred
    accuracy = (tp + tn + na_correct) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "na_correct": na_correct,
        "na_wrong": na_wrong,
        "wrong_na_pred": wrong_na_pred,
        "not_applicable_count": na_correct + na_wrong,  # kept for backward compat with report
        "n": total,                    # scored conversations (all with a GT label) — for CI / gating
        "evaluable_n": tp + tn + fp + fn,  # Yes/No answer rows only — the fragile dimension
    }
