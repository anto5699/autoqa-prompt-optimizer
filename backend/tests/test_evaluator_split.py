# backend/tests/test_evaluator_split.py
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

V1_RULE = {
    "rule_id": "greeting", "rule_type": "answer", "version": "v1",
    "speaker": "agent", "evaluation_type": "entire", "n_messages": 0,
    "current_description": "Agent greets.", "current_predictions": {},
    "current_rationales": {}, "iteration_history": [], "status": "pending",
    "current_accuracy": 0.0, "current_precision": 0.0, "current_recall": 0.0,
    "current_f1": 0.0, "true_positives": 0, "false_positives": 0,
    "true_negatives": 0, "false_negatives": 0, "not_applicable_count": 0,
    "rca_findings": None, "alignment_audit": None, "audit_iteration": None,
    "optimization_notes": None, "initial_accuracy": None, "best_accuracy": None,
    "best_description": None, "best_trigger_description": None,
    "trigger_description": None, "trigger_speaker": None,
    "original_description": "Agent greets.",
}

V2_RULE = {**V1_RULE, "rule_id": "empathy", "version": "v2",
           "rule_type": "answer", "current_description": "CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent listens.\nEXCEPTION: None."}

CONV = {"conversation_id": "c1", "transcript": [{"speaker": "customer", "msg": "Hello"}]}

@pytest.mark.asyncio
async def test_evaluator_makes_separate_calls_per_version():
    """One LLM call for V1 rules, one for V2 rules (per conversation)."""
    records = {"greeting": V1_RULE, "empathy": V2_RULE}

    v1_response = MagicMock()
    v1_response.content = '[{"_id":"greeting","isQualified":true,"rationale":"Greeted."}]'
    v2_response = MagicMock()
    v2_response.content = '[{"_id":"empathy","isQualified":true,"justification":"Listened."}]'

    call_count = 0
    async def fake_ainvoke(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        # first call = V1, second call = V2
        return v1_response if call_count == 1 else v2_response

    mock_llm = MagicMock()
    mock_llm.ainvoke = fake_ainvoke

    from agents.nodes.evaluator import _evaluate_conversation
    import asyncio
    sem = asyncio.Semaphore(5)

    conv_id, results = await _evaluate_conversation(
        CONV, records, "V1_PROMPT", "V2_PROMPT", "en", mock_llm, sem, batch_size=6
    )

    assert call_count == 2  # one V1 call + one V2 call
    assert conv_id == "c1"

@pytest.mark.asyncio
async def test_v2_result_uses_justification_as_rationale():
    records = {"empathy": V2_RULE}
    v2_response = MagicMock()
    v2_response.content = '[{"_id":"empathy","isQualified":false,"justification":"Agent did not listen to customer concern."}]'

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=v2_response)

    from agents.nodes.evaluator import _evaluate_conversation
    import asyncio
    sem = asyncio.Semaphore(5)

    conv_id, results = await _evaluate_conversation(
        CONV, records, "V1_PROMPT", "V2_PROMPT", "en", mock_llm, sem, batch_size=6
    )
    pred_update = next((r for r in results if r.get("_id") == "empathy"), {})
    # V2 verdict: isQualified=false → "No"
    assert conv_id == "c1"
    # justification field must be surfaced as the rationale
    assert len(pred_update.get("rationale", "")) > 0
    assert "Agent did not listen to customer concern." in pred_update.get("rationale", "")
