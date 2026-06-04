import asyncio
from unittest.mock import AsyncMock, patch

from agents.nodes.evaluator import evaluator


def _record(rule_id, *, status="optimizing", predictions=None):
    return {
        "rule_id": rule_id,
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        "current_description": "test description",
        "iteration_history": [],
        "current_predictions": predictions or {},
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


def _state(records):
    return {
        "session_id": "test",
        "conversations": [
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
def test_converged_predictions_not_reset(mock_eval_conv):
    """Converged rule predictions must not be cleared before evaluation pass."""
    converged_preds = {"c1": "Yes", "c2": "No"}
    records = {
        "r_conv": _record("r_conv", status="converged", predictions=converged_preds.copy()),
        "r_active": _record("r_active", status="optimizing"),
    }

    mock_eval_conv.side_effect = [
        ("c1", [{"_id": "r_active", "isQualified": True}]),
        ("c2", [{"_id": "r_active", "isQualified": False}]),
    ]

    result = asyncio.run(evaluator(_state(records)))

    assert result["parameter_records"]["r_conv"]["current_predictions"] == converged_preds
    assert result["parameter_records"]["r_active"]["current_predictions"] == {"c1": "Yes", "c2": "No"}


@patch("agents.nodes.evaluator._evaluate_conversation", new_callable=AsyncMock)
def test_all_converged_early_return(mock_eval_conv):
    """When all rules are converged, evaluator must return early without any LLM calls."""
    records = {
        "r1": _record("r1", status="converged", predictions={"c1": "Yes"}),
        "r2": _record("r2", status="converged", predictions={"c1": "No"}),
    }

    result = asyncio.run(evaluator(_state(records)))

    mock_eval_conv.assert_not_called()
    assert result["parameter_records"]["r1"]["current_predictions"] == {"c1": "Yes"}
    assert result["parameter_records"]["r2"]["current_predictions"] == {"c1": "No"}
    assert result["current_phase"] == "benchmarking"


@patch("agents.nodes.evaluator._evaluate_conversation", new_callable=AsyncMock)
def test_converged_rule_excluded_from_llm_payload(mock_eval_conv):
    """_evaluate_conversation must never receive converged rules in its parameter_records arg."""
    converged_preds = {"c1": "Yes"}
    records = {
        "r_conv": _record("r_conv", status="converged", predictions=converged_preds.copy()),
        "r_active": _record("r_active", status="optimizing"),
    }

    mock_eval_conv.return_value = ("c1", [{"_id": "r_active", "isQualified": False}])

    asyncio.run(evaluator(_state(records)))

    for call in mock_eval_conv.call_args_list:
        payload_records = call.args[1]  # second positional arg is parameter_records
        assert "r_conv" not in payload_records, "converged rule must not be in LLM payload"
        assert "r_active" in payload_records
