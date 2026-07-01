import asyncio
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from agents.nodes.rca_analyzer import _collect_error_cases, rca_analyzer


def _record(rule_id, *, predictions, rationales=None):
    return {
        "rule_id": rule_id,
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        "current_description": "Agent must greet the customer",
        "iteration_history": [],
        "current_predictions": predictions,
        "current_rationales": rationales or {},
        "current_accuracy": 0.5,
        "current_precision": 0.5,
        "current_recall": 0.5,
        "current_f1": 0.5,
        "true_positives": 1,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 1,
        "not_applicable_count": 0,
        "rca_findings": None,
        "optimization_notes": None,
        "status": "optimizing",
        "initial_accuracy": 0.5,
        "best_accuracy": 0.5,
        "best_description": None,
    }


@patch("agents.nodes.rca_analyzer.get_llm")
def test_rca_prompt_contains_evaluator_rationale(mock_get_llm):
    """RCA HumanMessage contains the evaluator's stated reason and the framing sentence."""
    captured: list = []

    mock_llm = MagicMock()
    mock_llm.model_name = "gpt-4o"

    async def fake_ainvoke(messages):
        captured.extend(messages)
        return MagicMock(content="Root cause: The wording is vague.")

    mock_llm.ainvoke = fake_ainvoke
    mock_get_llm.return_value = mock_llm

    state = {
        "session_id": "test",
        "current_iteration": 1,
        "parameters_below_target": ["r1"],
        "parameter_records": {
            "r1": _record(
                "r1",
                predictions={"c1": "No"},
                rationales={"c1": "Agent did not explicitly say hello"},
            )
        },
        "ground_truth_map": {"c1": {"r1": "Yes"}},
        "conversations": [{"conversation_id": "c1", "transcript": []}],
        "llm_config": {},
        "progress_log": [],
    }

    asyncio.run(rca_analyzer(state))

    human_msg = next(m for m in captured if isinstance(m, HumanMessage))
    assert "Agent did not explicitly say hello" in human_msg.content
    assert "Treat it as evidence" in human_msg.content


def test_collect_error_cases_excludes_na_ground_truths():
    """Conversations with NA ground truth must produce no error cases."""
    errors = _collect_error_cases(
        rule_id="r1",
        predictions={"c1": "Yes", "c2": "No"},
        rationales={},
        ground_truth_map={"c1": {"r1": "NA"}, "c2": {"r1": "NA"}},
        conversations_by_id={},
    )
    assert errors == []
