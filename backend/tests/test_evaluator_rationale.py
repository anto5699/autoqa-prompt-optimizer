import asyncio
from unittest.mock import AsyncMock, patch

from agents.nodes.evaluator import evaluator


def _record(rule_id, *, status="optimizing", predictions=None, rationales=None):
    return {
        "rule_id": rule_id,
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        "current_description": "test description",
        "iteration_history": [],
        "current_predictions": predictions or {},
        "current_rationales": rationales or {},
        "current_accuracy": 0.0,
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


def _state(records, *, conversations=None):
    return {
        "session_id": "test",
        "conversations": conversations or [
            {"conversation_id": "c1", "transcript": []},
            {"conversation_id": "c2", "transcript": []},
        ],
        "parameter_records": records,
        "system_prompt": "system",
        "language": "en",
        "current_iteration": 1,
        "progress_log": [],
    }


@patch("agents.nodes.evaluator._evaluate_conversation", new_callable=AsyncMock)
def test_evaluator_captures_rationale(mock_eval_conv):
    """Rationale returned by the LLM is stored alongside the prediction."""
    records = {"r1": _record("r1")}
    mock_eval_conv.side_effect = [
        ("c1", [{"_id": "r1", "isQualified": True, "rationale": "Agent said hello"}]),
        ("c2", [{"_id": "r1", "isQualified": False, "rationale": "Agent skipped greeting"}]),
    ]

    result = asyncio.run(evaluator(_state(records)))

    assert result["parameter_records"]["r1"]["current_predictions"] == {"c1": "Yes", "c2": "No"}
    assert result["parameter_records"]["r1"]["current_rationales"]["c1"] == "Agent said hello"
    assert result["parameter_records"]["r1"]["current_rationales"]["c2"] == "Agent skipped greeting"


@patch("agents.nodes.evaluator._evaluate_conversation", new_callable=AsyncMock)
def test_evaluator_rationale_truncated_at_500(mock_eval_conv):
    """Rationale longer than 500 chars is truncated to exactly 500."""
    long_rationale = "x" * 600
    records = {"r1": _record("r1")}
    mock_eval_conv.return_value = ("c1", [{"_id": "r1", "isQualified": True, "rationale": long_rationale}])

    result = asyncio.run(evaluator(_state(records, conversations=[{"conversation_id": "c1", "transcript": []}])))

    stored = result["parameter_records"]["r1"]["current_rationales"]["c1"]
    assert len(stored) == 500


@patch("agents.nodes.evaluator._evaluate_conversation", new_callable=AsyncMock)
def test_failure_path_defaults_rationale_to_empty(mock_eval_conv):
    """When a conversation errors, rationale defaults to '' with same keys as predictions."""
    records = {"r1": _record("r1")}
    # c1 succeeds, c2 raises — failure_count=1 < total=2 so no RuntimeError
    mock_eval_conv.side_effect = [
        ("c1", [{"_id": "r1", "isQualified": True, "rationale": "ok"}]),
        RuntimeError("LLM unavailable"),
    ]

    result = asyncio.run(evaluator(_state(records)))

    preds = result["parameter_records"]["r1"]["current_predictions"]
    rats = result["parameter_records"]["r1"]["current_rationales"]
    assert set(preds.keys()) == set(rats.keys())
    # c2 failed — defaulted
    assert preds["c2"] == "No"
    assert rats["c2"] == ""
    # c1 succeeded — captured normally
    assert preds["c1"] == "Yes"
    assert rats["c1"] == "ok"
