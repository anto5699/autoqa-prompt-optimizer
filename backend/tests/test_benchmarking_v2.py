# backend/tests/test_benchmarking_v2.py
import asyncio
import pytest
from agents.nodes.benchmarking import benchmarking

def _v2_record(predictions, rule_id="greeting"):
    return {
        "rule_id": rule_id, "version": "v2", "rule_type": "answer",
        "speaker": "agent", "evaluation_type": "entire", "n_messages": 0,
        "current_description": "CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent greets.\nEXCEPTION: None.",
        "trigger_description": None, "trigger_speaker": None,
        "current_predictions": predictions, "current_rationales": {},
        "current_accuracy": 0.0, "current_precision": 0.0, "current_recall": 0.0,
        "current_f1": 0.0, "true_positives": 0, "false_positives": 0,
        "true_negatives": 0, "false_negatives": 0, "not_applicable_count": 0,
        "rca_findings": None, "alignment_audit": None, "audit_iteration": None,
        "optimization_notes": None, "status": "pending",
        "initial_accuracy": None, "best_accuracy": None,
        "best_description": None, "best_trigger_description": None,
        "original_description": "Agent greets.", "iteration_history": [],
    }

def _state(records, gt_map):
    return {
        "session_id": "s1", "system_prompt": "SP", "system_prompt_v2": "SP2",
        "language": "en", "llm_config": {}, "conversations": [],
        "rules": [], "ground_truth_map": gt_map, "excluded_rules": [],
        "clarifying_questions": [], "user_answers": {}, "clarification_complete": True,
        "clarified_rule_ids": [], "current_iteration": 1, "max_iterations": 8,
        "accuracy_target": 0.90, "parameter_records": records,
        "optimization_complete": False, "parameters_meeting_target": [],
        "parameters_below_target": list(records.keys()),
        "progress_log": [], "current_phase": "benchmarking", "final_report": None,
        "skip_setup": False,
    }

def test_v2_na_excluded_from_denominator():
    """NA ground truths excluded from accuracy denominator for V2 parameters."""
    gt_map = {
        "c1": {"greeting": "Yes"}, "c2": {"greeting": "No"},
        "c3": {"greeting": "NA"},  # excluded
    }
    preds = {"c1": "Yes", "c2": "No", "c3": "NA"}
    record = _v2_record(preds)
    state = _state({"greeting": record}, gt_map)
    result = asyncio.run(benchmarking(state))
    rec = result["parameter_records"]["greeting"]
    # 2 correct out of 2 non-NA = 100%
    assert rec["current_accuracy"] == pytest.approx(1.0)

def test_v2_no_best_trigger_description_tracking():
    """V2 records must never set best_trigger_description."""
    gt_map = {"c1": {"greeting": "Yes"}, "c2": {"greeting": "No"}}
    preds = {"c1": "Yes", "c2": "No"}
    record = _v2_record(preds)
    state = _state({"greeting": record}, gt_map)
    result = asyncio.run(benchmarking(state))
    rec = result["parameter_records"]["greeting"]
    assert rec.get("best_trigger_description") is None
