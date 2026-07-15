"""V2 agent evals for the evaluator node.

Scenarios
---------
E-V2-1  Correct V2 verdict from a clear greeting conversation
E-V2-2  V2 system prompt is used (V1 is not); V2 payload uses scope/n_turns
E-V2-3  V2 justification field mapped to rationale (mocked LLM)
E-V2-4  V2 adherence='NO' maps to prediction 'No' (mocked LLM)
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from agents.nodes.evaluator import evaluator
from config import DEFAULT_SYSTEM_PROMPT_V2
from tests.evals.fixtures.state_factory import build_state


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _v2_greeting_rule(rule_id: str = "AgentGreetingV2") -> dict:
    return {
        "rule_id": rule_id,
        "version": "v2",
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": -1,
        "description": "CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent greets the customer.\nEXCEPTION: None.",
    }


def _v1_greeting_rule(rule_id: str = "AgentGreetingV1") -> dict:
    return {
        "rule_id": rule_id,
        "version": "v1",
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": -1,
        "description": (
            "METRIC_NAME: Agent Greeting\n"
            "SPEAKER: Agent\n"
            "ACTION: Greets the customer at the start of the call\n"
            "PASS_LOGIC: ALL\n"
            "PASS_CRITERIA:\n"
            "1. Agent says hello or a greeting word in the first exchange\n"
        ),
    }


def _greeting_conversation(conv_id: str = "c1") -> dict:
    return {
        "id": conv_id,
        "transcript": [
            {"speaker": "agent", "msg": "Good morning! Thank you for calling. How can I help you today?"},
            {"speaker": "customer", "msg": "Hi, I have a billing question."},
        ],
        "ground_truth": "Yes",
    }


# ---------------------------------------------------------------------------
# E-V2-1: Correct V2 verdict from a clearly greeting conversation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e_v2_1_correct_verdict():
    """Evaluator correctly returns 'Yes' for a V2 rule when agent clearly greets."""
    scenario = {
        "id": "e-v2-1",
        "rule": _v2_greeting_rule(),
        "conversations": [_greeting_conversation()],
    }
    state = build_state(scenario)
    result = await evaluator(state)

    records = result["parameter_records"]
    rule_id = "AgentGreetingV2"
    prediction = records[rule_id]["current_predictions"].get("c1")
    rationale = records[rule_id]["current_rationales"].get("c1", "")

    assert prediction == "Yes", (
        f"[E-V2-1] Expected prediction='Yes' for clear greeting, got '{prediction}'"
    )
    assert len(rationale) > 0, (
        "[E-V2-1] Expected non-empty rationale captured from justification field"
    )


# ---------------------------------------------------------------------------
# E-V2-2: Mixed V1 + V2 scenario produces 2 LLM calls; V2 uses V2 system prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e_v2_2_system_prompt_routing():
    """Mixed V1+V2 scenario: evaluator makes 2 LLM calls; V2 call uses V2 system prompt, V1 does not."""
    # Build state using the multi-rule path: pass both rules in scenario["rules"]
    v1_rule = _v1_greeting_rule("AgentGreetingV1")
    v2_rule = _v2_greeting_rule("AgentGreetingV2")
    conv = _greeting_conversation("c1")

    scenario = {
        "id": "e-v2-2",
        "rules": [v1_rule, v2_rule],
        "conversations": [conv],
    }
    state = build_state(scenario)

    calls: list[dict] = []

    from langchain_openai import ChatOpenAI
    original_ainvoke = ChatOpenAI.ainvoke

    async def capturing_ainvoke(self, messages, **kwargs):
        call_info: dict = {"system_prompt": None, "user_content": None}
        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                if (
                    msg.content.startswith("You are an AutoQA evaluation engine")
                    or msg.content.startswith("You are a Conversation Quality Auditor")
                ):
                    call_info["system_prompt"] = msg.content[:80]
                elif msg.content.startswith("Transcripts:"):
                    call_info["user_content"] = msg.content
        calls.append(call_info)
        return await original_ainvoke(self, messages, **kwargs)

    with patch.object(ChatOpenAI, "ainvoke", capturing_ainvoke):
        await evaluator(state)

    assert len(calls) == 2, (
        f"[E-V2-2] Expected 2 LLM calls (one V1, one V2), got {len(calls)}. Calls: {calls}"
    )

    system_prompts = [c["system_prompt"] for c in calls]

    assert any(
        p and p.startswith("You are a Conversation Quality Auditor")
        for p in system_prompts
    ), (
        f"[E-V2-2] V2 system prompt was not used in any call. Captured: {system_prompts}"
    )

    assert any(
        p and not p.startswith("You are a Conversation Quality Auditor")
        for p in system_prompts
    ), (
        f"[E-V2-2] V1 system prompt was not used in any call. Captured: {system_prompts}"
    )

    # The V2 rule payload must use the turn-based scope contract, not the message-based fields.
    v2_payloads = [
        c["user_content"] for c in calls
        if c["system_prompt"] and c["system_prompt"].startswith("You are a Conversation Quality Auditor")
    ]
    assert v2_payloads and v2_payloads[0], "[E-V2-2] Could not capture the V2 call user payload"
    v2_payload = v2_payloads[0]
    assert '"scope"' in v2_payload and '"n_turns"' in v2_payload, (
        "[E-V2-2] V2 rule payload should serialize scope/n_turns"
    )
    assert '"evaluation_type"' not in v2_payload and '"n_messages"' not in v2_payload, (
        "[E-V2-2] V2 rule payload should not use the legacy evaluation_type/n_messages fields"
    )


# ---------------------------------------------------------------------------
# E-V2-3: V2 justification field mapped to rationale (mocked LLM response)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e_v2_3_justification_mapped_to_rationale():
    """V2 LLM response justification is stored in current_rationales (mocked)."""
    import json as _json

    scenario = {
        "id": "e-v2-3",
        "rule": _v2_greeting_rule(),
        "conversations": [_greeting_conversation()],
    }
    state = build_state(scenario)

    long_justification = "A" * 600
    mock_response = [
        {
            "_id": "AgentGreetingV2",
            "adherence": "YES",
            "speaker": "agent",
            "failureReason": "",
            "justification": long_justification,
            "messageIds": ["0"],
        }
    ]
    mock_content = _json.dumps(mock_response)

    mock_ai_message = AIMessage(content=mock_content)

    from langchain_openai import ChatOpenAI

    with patch.object(ChatOpenAI, "ainvoke", new_callable=AsyncMock, return_value=mock_ai_message):
        result = await evaluator(state)

    records = result["parameter_records"]
    prediction = records["AgentGreetingV2"]["current_predictions"].get("c1")
    rationale = records["AgentGreetingV2"]["current_rationales"].get("c1", "")

    assert prediction == "Yes", (
        f"[E-V2-3] Expected prediction='Yes' from adherence='YES', got '{prediction}'"
    )
    assert len(rationale) > 0, "[E-V2-3] Rationale should be non-empty after mapping justification"
    assert len(rationale) <= 500, (
        f"[E-V2-3] Rationale should be truncated to 500 chars, got {len(rationale)}"
    )


# ---------------------------------------------------------------------------
# E-V2-4: V2 adherence='NO' maps to prediction 'No' (mocked LLM response)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e_v2_4_adherence_no_maps_to_prediction():
    """A V2 response with adherence='NO' is mapped to prediction 'No' (mocked)."""
    import json as _json

    scenario = {
        "id": "e-v2-4",
        "rule": _v2_greeting_rule(),
        "conversations": [_greeting_conversation()],
    }
    state = build_state(scenario)

    mock_response = [
        {
            "_id": "AgentGreetingV2",
            "adherence": "NO",
            "speaker": "agent",
            "failureReason": "Agent did not greet the customer",
            "justification": "The agent never offered any greeting at the start of the conversation.",
            "messageIds": [],
        }
    ]
    mock_ai_message = AIMessage(content=_json.dumps(mock_response))

    from langchain_openai import ChatOpenAI

    with patch.object(ChatOpenAI, "ainvoke", new_callable=AsyncMock, return_value=mock_ai_message):
        result = await evaluator(state)

    records = result["parameter_records"]
    prediction = records["AgentGreetingV2"]["current_predictions"].get("c1")

    assert prediction == "No", (
        f"[E-V2-4] Expected prediction='No' from adherence='NO', got '{prediction}'"
    )
