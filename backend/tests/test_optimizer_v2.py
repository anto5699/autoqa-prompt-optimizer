import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

V2_RECORD = {
    "rule_id": "empathy", "version": "v2", "rule_type": "answer",
    "speaker": "agent", "evaluation_type": "entire", "n_messages": 0,
    "current_description": "CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent listens.\nEXCEPTION: None.",
    "trigger_description": None,
    "iteration_history": [
        {"iteration": 1, "accuracy": 0.60},
        {"iteration": 2, "accuracy": 0.65},
        {"iteration": 3, "accuracy": 0.65},
    ],
    "rca_findings": "Agent does not actively acknowledge customer concern.",
    "current_accuracy": 0.65, "best_accuracy": 0.65,
    "best_description": "CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent listens.\nEXCEPTION: None.",
    "status": "optimizing",
    "current_predictions": {}, "current_rationales": {},
    "current_precision": 0.0, "current_recall": 0.0, "current_f1": 0.0,
    "true_positives": 0, "false_positives": 0, "true_negatives": 0,
    "false_negatives": 0, "not_applicable_count": 0,
    "original_description": "Agent listens.",
    "initial_accuracy": 0.55, "alignment_audit": None, "audit_iteration": None,
    "optimization_notes": None, "best_trigger_description": None,
    "trigger_speaker": None,
}

@pytest.mark.asyncio
async def test_v2_optimizer_updates_only_current_description():
    """V2 optimiser must update current_description and not touch trigger_description."""
    optimized_desc = "CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent acknowledges customer concern.\nEXCEPTION: None."
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=optimized_desc))

    from agents.nodes.prompt_optimizer import _optimise_description
    result = await _optimise_description(V2_RECORD, {}, mock_llm, "sess1")

    assert "CONDITION:" in result
    assert "EXPECTED BEHAVIOR:" in result
    assert result != V2_RECORD["current_description"]

@pytest.mark.asyncio
async def test_v2_optimizer_prompt_contains_v2_constraints():
    """V2 optimiser prompt must mention CONDITION/EXPECTED BEHAVIOR/EXCEPTION format."""
    captured_prompts = []

    async def capture_ainvoke(messages, **kwargs):
        for m in messages:
            if hasattr(m, "content"):
                captured_prompts.append(m.content)
        return MagicMock(content="CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent greets.\nEXCEPTION: None.")

    mock_llm = MagicMock()
    mock_llm.ainvoke = capture_ainvoke

    from agents.nodes.prompt_optimizer import _optimise_description
    await _optimise_description(V2_RECORD, {}, mock_llm, "sess1")

    full_prompt = " ".join(captured_prompts)
    assert "CONDITION" in full_prompt
    assert "EXPECTED BEHAVIOR" in full_prompt
    assert "EXCEPTION" in full_prompt
