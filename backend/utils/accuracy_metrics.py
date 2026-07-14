from typing import Dict


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
    }
