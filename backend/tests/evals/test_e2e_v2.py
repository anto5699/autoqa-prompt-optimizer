"""V2 agent evals — end-to-end scenarios.

Scenarios
---------
ETE-V2-1  Mixed V1/V2 session converges; both parameters have 'version' in final report
ETE-V2-2  All-V2 session: after 1 iteration all final_prompt values pass _is_structured_v2()
"""
import json

import pytest

from agents.graph import graph_app
from agents.nodes.baseline_prompt_generator import _is_structured_v2
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output


# ---------------------------------------------------------------------------
# Shared scenario builders
# ---------------------------------------------------------------------------

_V1_INTRO_DESC = (
    "METRIC_NAME: Agent Introduction\n"
    "SPEAKER: Agent\n"
    "ACTION: Introduces themselves by name at the start of the call\n"
    "PASS_LOGIC: ALL\n"
    "PASS_CRITERIA:\n"
    "1. Agent says their own name in the first 4 messages\n"
    "EXAMPLES:\n"
    "PASS:\n"
    "1. \"Hi, I'm Alex from customer support.\"\n"
    "FAIL:\n"
    "1. \"Hello, how can I help you today?\"\n"
)

_V2_GREETING_DESC = (
    "CONDITION: Always.\n"
    "EXPECTED BEHAVIOR:\n"
    "  - Agent greets the customer.\n"
    "EXCEPTION: None."
)


def _mixed_scenario() -> dict:
    """One V1 rule + one V2 rule, easy conversations for quick convergence."""
    return {
        "id": "ete-v2-1",
        "e2e": {
            "max_iterations": 3,
            "accuracy_target": 0.80,
        },
        "rules": [
            {
                "rule_id": "AgentIntroV1",
                "version": "v1",
                "rule_type": "answer",
                "speaker": "Agent",
                "evaluation_type": "first",
                "n_messages": 4,
                "description": _V1_INTRO_DESC,
            },
            {
                "rule_id": "AgentGreetingV2",
                "version": "v2",
                "rule_type": "answer",
                "speaker": "Agent",
                "evaluation_type": "entire",
                "n_messages": -1,
                "description": _V2_GREETING_DESC,
            },
        ],
        "conversations": [
            {
                "id": "c1",
                "transcript": [
                    {"speaker": "agent", "msg": "Thank you for calling. My name is Jordan. How can I help?"},
                    {"speaker": "customer", "msg": "Hi Jordan, I have a billing question."},
                ],
                "ground_truth": {"AgentIntroV1": "Yes", "AgentGreetingV2": "Yes"},
            },
            {
                "id": "c2",
                "transcript": [
                    {"speaker": "agent", "msg": "Hello! Good morning. How can I assist you today?"},
                    {"speaker": "customer", "msg": "I need to update my address."},
                ],
                "ground_truth": {"AgentIntroV1": "No", "AgentGreetingV2": "Yes"},
            },
            {
                "id": "c3",
                "transcript": [
                    {"speaker": "agent", "msg": "Good afternoon, this is Sam speaking."},
                    {"speaker": "customer", "msg": "I'd like to cancel my subscription."},
                ],
                "ground_truth": {"AgentIntroV1": "Yes", "AgentGreetingV2": "Yes"},
            },
            {
                "id": "c4",
                "transcript": [
                    {"speaker": "agent", "msg": "Welcome to support. How may I help?"},
                    {"speaker": "customer", "msg": "I have a technical issue."},
                ],
                "ground_truth": {"AgentIntroV1": "No", "AgentGreetingV2": "Yes"},
            },
        ],
    }


def _all_v2_scenario() -> dict:
    """Two V2 rules with pre-structured V2 descriptions; validates V2 format is preserved end-to-end.

    Note: E2E scenarios use skip_setup=True so baseline_prompt_generator is bypassed.
    The descriptions start already structured so we can verify the optimizer preserves
    V2 format throughout the full evaluation → benchmarking → (optional RCA) → finalize loop.
    """
    return {
        "id": "ete-v2-2",
        "e2e": {
            "max_iterations": 2,
            "accuracy_target": 0.80,
        },
        "rules": [
            {
                "rule_id": "AgentGreetingAllV2",
                "version": "v2",
                "rule_type": "answer",
                "speaker": "Agent",
                "evaluation_type": "entire",
                "n_messages": -1,
                "description": (
                    "CONDITION: Always.\n"
                    "EXPECTED BEHAVIOR:\n"
                    "  - Agent greets the customer at the beginning of the call.\n"
                    "EXCEPTION: None."
                ),
            },
            {
                "rule_id": "AgentClosingAllV2",
                "version": "v2",
                "rule_type": "answer",
                "speaker": "Agent",
                "evaluation_type": "entire",
                "n_messages": -1,
                "description": (
                    "CONDITION: Always.\n"
                    "EXPECTED BEHAVIOR:\n"
                    "  - Agent thanks the customer and closes the call professionally.\n"
                    "EXCEPTION: None."
                ),
            },
        ],
        "conversations": [
            {
                "id": "c1",
                "transcript": [
                    {"speaker": "agent", "msg": "Hello! Thank you for calling. How can I help you today?"},
                    {"speaker": "customer", "msg": "I need help with my account."},
                    {"speaker": "agent", "msg": "Of course. Let me look into that."},
                    {"speaker": "customer", "msg": "Thank you."},
                    {"speaker": "agent", "msg": "Is there anything else I can help you with? Thank you for calling!"},
                ],
                "ground_truth": {"AgentGreetingAllV2": "Yes", "AgentClosingAllV2": "Yes"},
            },
            {
                "id": "c2",
                "transcript": [
                    {"speaker": "agent", "msg": "Good morning! How may I assist you?"},
                    {"speaker": "customer", "msg": "I'd like to cancel my subscription."},
                    {"speaker": "agent", "msg": "I have processed your request. Thank you and have a great day!"},
                ],
                "ground_truth": {"AgentGreetingAllV2": "Yes", "AgentClosingAllV2": "Yes"},
            },
            {
                "id": "c3",
                "transcript": [
                    {"speaker": "agent", "msg": "Welcome to customer support! I'm Morgan."},
                    {"speaker": "customer", "msg": "Hi, I have a billing question."},
                    {"speaker": "agent", "msg": "I hope I was able to help. Thank you for calling us today!"},
                ],
                "ground_truth": {"AgentGreetingAllV2": "Yes", "AgentClosingAllV2": "Yes"},
            },
        ],
    }


# ---------------------------------------------------------------------------
# ETE-V2-1: Mixed V1/V2 session — both parameters have 'version' in final report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ete_v2_1_mixed_session(eval_llm):
    """Mixed V1/V2 session completes; final report contains 'version' for both parameters."""
    scenario = _mixed_scenario()
    state = build_state(scenario)
    config = {"configurable": {"thread_id": f"eval-{scenario['id']}"}}

    result = await graph_app.ainvoke(state, config=config)

    assert result.get("final_report") is not None, (
        "[ETE-V2-1] Session did not produce a final_report"
    )

    param_records = result.get("parameter_records", {})
    for rule_id in ["AgentIntroV1", "AgentGreetingV2"]:
        assert rule_id in param_records, f"[ETE-V2-1] Missing parameter record for {rule_id}"
        rec = param_records[rule_id]
        assert "version" in rec, (
            f"[ETE-V2-1] Parameter record for {rule_id} missing 'version' field"
        )

    assert param_records["AgentIntroV1"]["version"] == "v1", (
        "[ETE-V2-1] AgentIntroV1 should have version='v1'"
    )
    assert param_records["AgentGreetingV2"]["version"] == "v2", (
        "[ETE-V2-1] AgentGreetingV2 should have version='v2'"
    )

    # Check that parameters_meeting_target or parameters_below_target are populated
    meeting = result.get("parameters_meeting_target", [])
    below = result.get("parameters_below_target", [])
    total = len(meeting) + len(below)
    assert total == 2, (
        f"[ETE-V2-1] Expected 2 total parameters in meeting+below, got {total} "
        f"(meeting={meeting}, below={below})"
    )

    # Judge the overall session summary
    summary = json.dumps({
        "optimization_complete": result.get("optimization_complete"),
        "current_iteration": result.get("current_iteration"),
        "final_report_present": result.get("final_report") is not None,
        "parameter_versions": {
            rid: rec.get("version")
            for rid, rec in param_records.items()
        },
        "parameters_meeting_target": meeting,
        "parameters_below_target": below,
    }, indent=2)

    judge_config = {
        "dimensions": [
            {
                "id": "session_completed",
                "weight": 0.40,
                "prompt": (
                    "Session summary (JSON):\n{output}\n\n"
                    "Did the session complete without error? Check that final_report_present=true "
                    "and optimization_complete is set."
                ),
            },
            {
                "id": "version_tracking",
                "weight": 0.60,
                "prompt": (
                    "Session summary (JSON):\n{output}\n\n"
                    "Does the summary show parameter_versions with 'v1' for AgentIntroV1 "
                    "and 'v2' for AgentGreetingV2?"
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(summary, judge_config, eval_llm, scenario_id="ete-v2-1")
    assert score.passed, f"[ETE-V2-1] {score}"


# ---------------------------------------------------------------------------
# ETE-V2-2: All-V2 session produces V2-formatted final prompts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ete_v2_2_all_v2_final_prompts(eval_llm):
    """All-V2 session: after baseline + 1 iteration, final_prompt values pass _is_structured_v2."""
    scenario = _all_v2_scenario()
    state = build_state(scenario)
    config = {"configurable": {"thread_id": f"eval-{scenario['id']}"}}

    result = await graph_app.ainvoke(state, config=config)

    assert result.get("final_report") is not None, (
        "[ETE-V2-2] Session did not produce a final_report"
    )

    param_records = result.get("parameter_records", {})

    for rule_id in ["AgentGreetingAllV2", "AgentClosingAllV2"]:
        assert rule_id in param_records, f"[ETE-V2-2] Missing parameter record for {rule_id}"
        final_prompt = param_records[rule_id].get("current_description", "")
        assert _is_structured_v2(final_prompt), (
            f"[ETE-V2-2] final_prompt for {rule_id} does not pass _is_structured_v2.\n"
            f"Prompt:\n{final_prompt}"
        )
        assert "METRIC_NAME" not in final_prompt, (
            f"[ETE-V2-2] V1 header 'METRIC_NAME' found in V2 final_prompt for {rule_id}"
        )

    # Judge the prompts
    greeting_prompt = param_records["AgentGreetingAllV2"]["current_description"]
    closing_prompt = param_records["AgentClosingAllV2"]["current_description"]
    combined = (
        f"AgentGreetingAllV2:\n{greeting_prompt}\n\n"
        f"AgentClosingAllV2:\n{closing_prompt}"
    )

    judge_config = {
        "dimensions": [
            {
                "id": "v2_format_all",
                "weight": 0.60,
                "prompt": (
                    "Two V2 final prompts:\n{output}\n\n"
                    "Do BOTH prompts use V2 Unified Criteria format with CONDITION, "
                    "EXPECTED BEHAVIOR, and EXCEPTION sections? "
                    "Score 1.0 if both comply, 0.5 if only one does, 0.0 if neither does."
                ),
            },
            {
                "id": "no_v1_headers",
                "weight": 0.40,
                "prompt": (
                    "Two V2 final prompts:\n{output}\n\n"
                    "Do the prompts avoid any V1-specific headers such as METRIC_NAME, "
                    "PASS_CRITERIA, PASS_LOGIC, or EXAMPLES sections?"
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(combined, judge_config, eval_llm, scenario_id="ete-v2-2")
    assert score.passed, f"[ETE-V2-2] {score}"
