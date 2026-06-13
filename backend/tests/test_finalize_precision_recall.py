import asyncio
import pytest


def _make_state(records):
    return {
        "session_id": "s1",
        "parameter_records": records,
        "parameters_below_target": [],
        "parameters_meeting_target": list(records.keys()),
        "current_iteration": 2,
        "accuracy_target": 0.9,
        "conversations": [{"id": "c1"}],
        "ground_truth_map": {"c1": {rid: "Yes" for rid in records}},
        "progress_log": [],
    }


def _record(rid, accuracy, precision, recall):
    return {
        "rule_id": rid, "rule_type": "answer", "speaker": "agent",
        "evaluation_type": "entire", "n_messages": 0,
        "current_description": "desc",
        "iteration_history": [{"iteration": 0, "accuracy": accuracy, "description": "desc"}],
        "current_predictions": {"c1": "Yes"},
        "current_accuracy": accuracy, "current_precision": precision,
        "current_recall": recall, "current_f1": 0.0,
        "true_positives": 1, "false_positives": 0,
        "true_negatives": 0, "false_negatives": 0,
        "not_applicable_count": 0,
        "rca_findings": None, "optimization_notes": None,
        "status": "converged",
        "initial_accuracy": accuracy, "best_accuracy": accuracy, "best_description": "desc",
    }


def test_overall_precision_and_recall_in_summary():
    from agents.nodes.finalize import finalize

    records = {
        "r1": _record("r1", 0.9, 0.8, 0.7),
        "r2": _record("r2", 0.85, 0.6, 0.9),
    }
    state = _make_state(records)
    result = asyncio.run(finalize(state))
    summary = result["final_report"]["summary"]

    assert "overall_precision" in summary
    assert "overall_recall" in summary
    assert abs(summary["overall_precision"] - 0.7) < 1e-6   # (0.8 + 0.6) / 2
    assert abs(summary["overall_recall"] - 0.8) < 1e-6      # (0.7 + 0.9) / 2


def test_overall_precision_recall_zero_when_no_records():
    from agents.nodes.finalize import finalize

    state = _make_state({})
    state["parameters_meeting_target"] = []
    result = asyncio.run(finalize(state))
    summary = result["final_report"]["summary"]

    assert summary["overall_precision"] == 0.0
    assert summary["overall_recall"] == 0.0
