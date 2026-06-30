from agents.state import OptimizationState, RuleRecord
from config import DEFAULT_SYSTEM_PROMPT


def build_state(scenario: dict) -> OptimizationState:
    """Build an OptimizationState from a YAML scenario dict."""
    rule = scenario["rule"]
    rule_id = rule["rule_id"]
    all_convs = list(scenario["conversations"]) + list(scenario.get("correct_conversations", []))

    conversations = [
        {"conversation_id": c["id"], "transcript": c.get("transcript", [])}
        for c in all_convs
    ]

    ground_truth_map: dict[str, dict[str, str]] = {
        c["id"]: {rule_id: c["ground_truth"]}
        for c in all_convs
        if "ground_truth" in c
    }

    current_predictions: dict[str, str] = {
        c["id"]: c["prediction"]
        for c in all_convs
        if "prediction" in c
    }

    # Compute confusion matrix
    tp = tn = fp = fn = na = 0
    for conv_id, pred in current_predictions.items():
        gt = ground_truth_map.get(conv_id, {}).get(rule_id, "NA")
        if gt == "NA":
            na += 1
        elif pred == gt:
            if gt == "Yes":
                tp += 1
            else:
                tn += 1
        else:
            if gt == "Yes":
                fn += 1
            else:
                fp += 1

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    history = scenario.get("iteration_history", [])

    record: RuleRecord = {
        "rule_id": rule_id,
        "rule_type": rule.get("rule_type", "answer"),
        "speaker": rule.get("speaker", "Agent"),
        "evaluation_type": rule.get("evaluation_type", "entire"),
        "n_messages": rule.get("n_messages", -1),
        "trigger_description": rule.get("trigger_description"),
        "trigger_speaker": rule.get("trigger_speaker"),
        "current_description": rule["description"],
        "iteration_history": history,
        "current_predictions": current_predictions,
        "current_rationales": {},
        "current_accuracy": accuracy,
        "current_precision": precision,
        "current_recall": recall,
        "current_f1": f1,
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "not_applicable_count": na,
        "rca_findings": scenario.get("rca_findings"),
        "alignment_audit": None,
        "audit_iteration": None,
        "optimization_notes": None,
        "status": scenario.get("rule_status", "optimizing"),
        "initial_accuracy": accuracy,
        "best_accuracy": accuracy,
        "best_description": rule["description"],
        "best_trigger_description": rule.get("trigger_description"),
        "original_description": rule["description"],
    }

    return {
        "session_id": f"eval-{scenario['id']}",
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "language": "en",
        "llm_config": {},
        "conversations": conversations,
        "rules": [rule],
        "ground_truth_map": ground_truth_map,
        "excluded_rules": [],
        "clarifying_questions": [],
        "user_answers": {},
        "clarification_complete": True,
        "clarified_rule_ids": [],
        "current_iteration": scenario.get("current_iteration", 1),
        "max_iterations": scenario.get("e2e", {}).get("max_iterations", 5),
        "accuracy_target": scenario.get("e2e", {}).get("accuracy_target", 0.90),
        "parameter_records": {rule_id: record},
        "optimization_complete": False,
        "parameters_meeting_target": [],
        "parameters_below_target": [rule_id],
        "progress_log": [],
        "current_phase": "analyzing_failures",
        "final_report": None,
        "skip_setup": True,
    }
