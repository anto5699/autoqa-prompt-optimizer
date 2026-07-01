from agents.state import OptimizationState, RuleRecord
from config import DEFAULT_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT_V2


def build_state(scenario: dict) -> OptimizationState:
    """Build an OptimizationState from a scenario dict.

    Handles both single-rule scenarios (rule: {...}) and multi-rule E2E scenarios
    (rules: [...]).  Supports V2 records via the 'version' field on each rule.
    """
    is_e2e = "e2e" in scenario
    raw_rules = scenario.get("rules") or [scenario["rule"]]
    all_convs = list(scenario.get("conversations", [])) + list(scenario.get("correct_conversations", []))

    conversations = [
        {"conversation_id": c["id"], "transcript": c.get("transcript", [])}
        for c in all_convs
    ]

    # --- Ground truth map ---
    def _get_gt(conv: dict, rule_id: str) -> str:
        gt = conv.get("ground_truth", "NA")
        if isinstance(gt, dict):
            return gt.get(rule_id, "NA")
        return gt

    ground_truth_map: dict[str, dict[str, str]] = {}
    for rule in raw_rules:
        rule_id = rule["rule_id"]
        for c in all_convs:
            ground_truth_map.setdefault(c["id"], {})[rule_id] = _get_gt(c, rule_id)

    # --- Build one RuleRecord per rule ---
    parameter_records: dict[str, RuleRecord] = {}
    all_rule_ids: list[str] = []

    for rule in raw_rules:
        rule_id = rule["rule_id"]
        all_rule_ids.append(rule_id)
        version = rule.get("version", "v1")

        current_predictions: dict[str, str] = {
            c["id"]: c["prediction"]
            for c in all_convs
            if "prediction" in c
        }

        # Confusion matrix (only for node-level tests that have pre-computed predictions)
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
            "version": version,
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
            "initial_accuracy": accuracy if not is_e2e else None,
            "best_accuracy": accuracy if not is_e2e else None,
            "best_description": rule["description"],
            "best_trigger_description": rule.get("trigger_description"),
            "original_description": rule["description"],
        }
        parameter_records[rule_id] = record

    e2e_cfg = scenario.get("e2e", {})

    return {
        "session_id": f"eval-{scenario['id']}",
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "system_prompt_v2": DEFAULT_SYSTEM_PROMPT_V2,
        "language": "en",
        "llm_config": {},
        "conversations": conversations,
        "rules": raw_rules,
        "ground_truth_map": ground_truth_map,
        "excluded_rules": [],
        "clarifying_questions": [],
        "user_answers": {},
        "clarification_complete": True,
        "clarified_rule_ids": all_rule_ids if is_e2e else [],
        "current_iteration": 0 if is_e2e else scenario.get("current_iteration", 1),
        "max_iterations": e2e_cfg.get("max_iterations", 5),
        "accuracy_target": e2e_cfg.get("accuracy_target", 0.90),
        "parameter_records": parameter_records,
        "optimization_complete": False,
        "parameters_meeting_target": [],
        "parameters_below_target": all_rule_ids,
        "progress_log": [],
        "current_phase": "evaluating" if is_e2e else "analyzing_failures",
        "final_report": None,
        "skip_setup": True,
    }
