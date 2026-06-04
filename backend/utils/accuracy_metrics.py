from typing import Dict


def compute_metrics(
    predictions: Dict[str, str],
    ground_truth_map: Dict[str, Dict[str, str]],
    rule_id: str,
) -> dict:
    """Compute TP/TN/FP/FN and derived metrics for a single rule.

    NA ground truths are excluded from all math.
    Denominator = TP + TN + FP + FN only.
    """
    tp = tn = fp = fn = na_count = 0

    for conv_id, gt_by_rule in ground_truth_map.items():
        gt = gt_by_rule.get(rule_id)
        if gt == "NA" or gt is None:
            na_count += 1
            continue

        pred = predictions.get(conv_id, "No")

        if gt == "Yes" and pred == "Yes":
            tp += 1
        elif gt == "No" and pred == "No":
            tn += 1
        elif gt == "No" and pred == "Yes":
            fp += 1
        elif gt == "Yes" and pred == "No":
            fn += 1

    denominator = tp + tn + fp + fn
    accuracy = (tp + tn) / denominator if denominator > 0 else 0.0
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
        "not_applicable_count": na_count,
    }
