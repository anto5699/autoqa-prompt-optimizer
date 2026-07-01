"""V2 agent evals for the baseline_prompt_generator node.

Scenarios
---------
B-V2-1  Generate mode produces valid V2 format
B-V2-2  Format mode converts plain text to V2 without changing meaning
B-V2-3  Already-structured V2 description is returned unchanged (zero LLM calls)
"""
import pytest
from unittest.mock import patch, AsyncMock

from agents.nodes.baseline_prompt_generator import baseline_prompt_generator, _is_structured_v2
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output


def _make_v2_rule(rule_id: str, description: str) -> dict:
    return {
        "rule_id": rule_id,
        "version": "v2",
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": -1,
        "description": description,
    }


def _make_scenario(rule_id: str, description: str, scene_id: str) -> dict:
    return {
        "id": scene_id,
        "rule": _make_v2_rule(rule_id, description),
        "conversations": [
            {
                "id": "c1",
                "transcript": [
                    {"speaker": "agent", "msg": "Hello, how can I help you today?"},
                    {"speaker": "customer", "msg": "I have a billing question."},
                ],
                "ground_truth": "Yes",
            }
        ],
    }


# ---------------------------------------------------------------------------
# B-V2-1: Generate mode produces valid V2 format
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_b_v2_1_generate_produces_v2_format(eval_llm):
    """Empty description triggers generate mode; output must have V2 format."""
    scenario = _make_scenario("agent_greeting_check", "", "b-v2-1")
    state = build_state(scenario)

    result = await baseline_prompt_generator(state)
    output = result["parameter_records"]["agent_greeting_check"]["current_description"]

    assert output, "[B-V2-1] baseline_prompt_generator returned empty description"

    judge_config = {
        "dimensions": [
            {
                "id": "has_condition",
                "weight": 0.35,
                "prompt": (
                    "V2 description output:\n{output}\n\n"
                    "Does the output contain a 'CONDITION:' section (case-insensitive) at or near the start?"
                ),
            },
            {
                "id": "has_expected_behavior",
                "weight": 0.35,
                "prompt": (
                    "V2 description output:\n{output}\n\n"
                    "Does the output contain an 'EXPECTED BEHAVIOR:' section?"
                ),
            },
            {
                "id": "has_exception",
                "weight": 0.30,
                "prompt": (
                    "V2 description output:\n{output}\n\n"
                    "Does the output contain an 'EXCEPTION:' section?"
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(output, judge_config, eval_llm, scenario_id="b-v2-1")
    assert score.passed, f"[B-V2-1] {score}"


# ---------------------------------------------------------------------------
# B-V2-2: Format mode converts plain text to V2 without changing meaning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_b_v2_2_format_converts_to_v2(eval_llm):
    """Plain-text description is reformatted to V2; core meaning is preserved."""
    plain_desc = "The agent must greet the customer at the beginning of every call."
    scenario = _make_scenario("agent_greeting_check_fmt", plain_desc, "b-v2-2")
    state = build_state(scenario)

    result = await baseline_prompt_generator(state)
    output = result["parameter_records"]["agent_greeting_check_fmt"]["current_description"]

    assert output, "[B-V2-2] baseline_prompt_generator returned empty description"

    # Structural check — must pass _is_structured_v2
    assert _is_structured_v2(output), (
        f"[B-V2-2] Output does not pass _is_structured_v2 check.\nOutput:\n{output}"
    )

    # _is_structured_v2 already asserts format above; judge checks semantic quality
    judge_config = {
        "dimensions": [
            {
                "id": "greeting_preserved",
                "weight": 0.70,
                "prompt": (
                    "Original plain-text description: 'The agent must greet the customer at the beginning of every call.'\n"
                    "Converted V2 description:\n{output}\n\n"
                    "Does the V2 description preserve the core requirement that the agent must greet the customer? "
                    "Score 1.0 if the greeting requirement is clearly present in EXPECTED BEHAVIOR or elsewhere."
                ),
            },
            {
                "id": "no_v1_headers",
                "weight": 0.30,
                "prompt": (
                    "Converted V2 description:\n{output}\n\n"
                    "Does the description avoid V1-only headers such as METRIC_NAME, PASS_CRITERIA, PASS_LOGIC, "
                    "or EXAMPLES? Score 1.0 if none of these V1 headers appear."
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(output, judge_config, eval_llm, scenario_id="b-v2-2")
    assert score.passed, f"[B-V2-2] {score}"


# ---------------------------------------------------------------------------
# B-V2-3: Already-structured V2 description is returned unchanged (zero LLM calls)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_b_v2_3_already_structured_no_llm_call():
    """Pre-structured V2 description is returned unchanged; LLM is never called."""
    structured_desc = (
        "CONDITION: Always.\n"
        "EXPECTED BEHAVIOR:\n"
        "  - Agent greets the customer.\n"
        "EXCEPTION: None."
    )
    scenario = _make_scenario("agent_greeting_check_prebuilt", structured_desc, "b-v2-3")
    state = build_state(scenario)

    llm_call_count = 0

    from langchain_openai import ChatOpenAI
    original_ainvoke = ChatOpenAI.ainvoke

    async def counting_ainvoke(self, messages, **kwargs):
        nonlocal llm_call_count
        llm_call_count += 1
        return await original_ainvoke(self, messages, **kwargs)

    with patch.object(ChatOpenAI, "ainvoke", counting_ainvoke):
        result = await baseline_prompt_generator(state)

    output = result["parameter_records"]["agent_greeting_check_prebuilt"]["current_description"]

    assert output == structured_desc, (
        f"[B-V2-3] Already-structured description should be unchanged.\n"
        f"Expected:\n{structured_desc}\nGot:\n{output}"
    )
    assert llm_call_count == 0, (
        f"[B-V2-3] Expected zero LLM calls for already-structured V2 description, got {llm_call_count}"
    )
