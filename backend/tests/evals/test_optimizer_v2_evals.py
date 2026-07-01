"""V2 agent evals for the prompt_optimizer node.

Scenarios
---------
O-V2-1  Optimised output conforms to V2 format and addresses RCA finding
O-V2-2  Stagnant V2 record triggers fundamental rewrite (Levenshtein similarity < 0.6)
O-V2-3  V2 optimiser never produces trigger/answer split
"""
import difflib

import pytest

from agents.nodes.prompt_optimizer import prompt_optimizer
from agents.nodes.baseline_prompt_generator import _is_structured_v2
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output


_GREETING_RCA = (
    "The EXPECTED BEHAVIOR does not specify what kind of greeting is required, "
    "causing false positives when agents say any word. "
    "Recommendation: add explicit requirement for a verbal greeting that includes "
    "a salutation (e.g., 'Hello', 'Good morning') directed at the customer."
)

_GREETING_DESC_V2 = (
    "CONDITION: Always.\n"
    "EXPECTED BEHAVIOR:\n"
    "  - Agent says a greeting word at the start of the call.\n"
    "EXCEPTION: None."
)


def _make_v2_scenario(
    rule_id: str,
    description: str,
    rca_findings: str,
    scene_id: str,
    *,
    iteration_history: list | None = None,
) -> dict:
    convs = [
        {
            "id": "c1",
            "transcript": [
                {"speaker": "agent", "msg": "Okay, let me check that for you."},
                {"speaker": "customer", "msg": "Thank you."},
            ],
            "ground_truth": "No",
            "prediction": "Yes",
        },
        {
            "id": "c2",
            "transcript": [
                {"speaker": "agent", "msg": "Alright, I can help with that."},
                {"speaker": "customer", "msg": "Great."},
            ],
            "ground_truth": "No",
            "prediction": "Yes",
        },
        {
            "id": "c3",
            "transcript": [
                {"speaker": "agent", "msg": "Hello! Good morning. How can I assist you?"},
                {"speaker": "customer", "msg": "I have a question."},
            ],
            "ground_truth": "Yes",
            "prediction": "Yes",
        },
    ]
    scenario: dict = {
        "id": scene_id,
        "rule": {
            "rule_id": rule_id,
            "version": "v2",
            "rule_type": "answer",
            "speaker": "Agent",
            "evaluation_type": "entire",
            "n_messages": -1,
            "description": description,
        },
        "rca_findings": rca_findings,
        "conversations": convs,
    }
    if iteration_history is not None:
        scenario["iteration_history"] = iteration_history
    return scenario


# ---------------------------------------------------------------------------
# O-V2-1: Optimised output conforms to V2 format and addresses RCA finding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_o_v2_1_optimised_output_v2_format(eval_llm):
    """Optimizer produces V2 format and addresses the RCA finding about greetings."""
    scenario = _make_v2_scenario(
        "AgentGreetingOpt",
        _GREETING_DESC_V2,
        _GREETING_RCA,
        "o-v2-1",
    )
    state = build_state(scenario)
    result = await prompt_optimizer(state)

    output = result["parameter_records"]["AgentGreetingOpt"]["current_description"]
    assert output, "[O-V2-1] prompt_optimizer returned empty description"

    assert _is_structured_v2(output), (
        f"[O-V2-1] Output does not pass _is_structured_v2.\nOutput:\n{output}"
    )

    # _is_structured_v2 already asserts V2 format; judge focuses on semantic quality
    judge_config = {
        "dimensions": [
            {
                "id": "rca_addressed",
                "weight": 0.70,
                "prompt": (
                    f"RCA finding: '{_GREETING_RCA}'\n\n"
                    "Optimised description:\n{output}\n\n"
                    "Does the EXPECTED BEHAVIOR section now specify that a verbal salutation or explicit "
                    "greeting word is required, addressing the RCA finding about vague greeting requirements?"
                ),
            },
            {
                "id": "no_v1_headers",
                "weight": 0.30,
                "prompt": (
                    "Optimised V2 description:\n{output}\n\n"
                    "Does the description avoid V1-only headers such as METRIC_NAME, PASS_CRITERIA, "
                    "PASS_LOGIC, or EXAMPLES? Score 1.0 if none of these V1 headers appear."
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(output, judge_config, eval_llm, scenario_id="o-v2-1")
    assert score.passed, f"[O-V2-1] {score}"


# ---------------------------------------------------------------------------
# O-V2-2: Stagnant V2 record triggers fundamental rewrite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_o_v2_2_stagnant_triggers_rewrite(eval_llm):
    """3 consecutive iterations at 0.65 accuracy triggers fundamental rewrite; similarity < 0.6."""
    stagnant_history = [
        {"iteration": 1, "accuracy": 0.65, "description": _GREETING_DESC_V2},
        {"iteration": 2, "accuracy": 0.65, "description": _GREETING_DESC_V2},
        {"iteration": 3, "accuracy": 0.65, "description": _GREETING_DESC_V2},
    ]
    scenario = _make_v2_scenario(
        "AgentGreetingStagnant",
        _GREETING_DESC_V2,
        _GREETING_RCA,
        "o-v2-2",
        iteration_history=stagnant_history,
    )
    state = build_state(scenario)
    result = await prompt_optimizer(state)

    output = result["parameter_records"]["AgentGreetingStagnant"]["current_description"]
    assert output, "[O-V2-2] prompt_optimizer returned empty description"

    similarity = difflib.SequenceMatcher(None, _GREETING_DESC_V2, output).ratio()

    assert _is_structured_v2(output), (
        f"[O-V2-2] Output does not pass _is_structured_v2.\nOutput:\n{output}"
    )

    judge_config = {
        "dimensions": [
            {
                "id": "meaningful_change",
                "weight": 0.60,
                "prompt": (
                    f"Original description:\n{_GREETING_DESC_V2}\n\n"
                    "Rewritten description:\n{output}\n\n"
                    "Is the rewritten description meaningfully different from the original — "
                    "not just minor word edits but a substantive change in the EXPECTED BEHAVIOR "
                    "or CONDITION clauses?"
                ),
            },
            {
                "id": "v2_format_retained",
                "weight": 0.40,
                "prompt": (
                    "Rewritten description:\n{output}\n\n"
                    "Does the rewritten description retain V2 Unified Criteria format "
                    "(CONDITION, EXPECTED BEHAVIOR, EXCEPTION)?"
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(output, judge_config, eval_llm, scenario_id="o-v2-2")
    assert score.passed, f"[O-V2-2] {score}"


# ---------------------------------------------------------------------------
# O-V2-3: V2 optimiser never produces trigger/answer split
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_o_v2_3_no_trigger_answer_split(eval_llm):
    """Optimised V2 output is a single block; no trigger/answer sections."""
    scenario = _make_v2_scenario(
        "AgentGreetingNoSplit",
        _GREETING_DESC_V2,
        _GREETING_RCA,
        "o-v2-3",
    )
    state = build_state(scenario)
    result = await prompt_optimizer(state)

    output = result["parameter_records"]["AgentGreetingNoSplit"]["current_description"]
    assert output, "[O-V2-3] prompt_optimizer returned empty description"

    assert "trigger" not in output.lower(), (
        f"[O-V2-3] Output should not contain 'trigger' but does.\nOutput:\n{output}"
    )
    assert "__answer" not in output.lower(), (
        f"[O-V2-3] Output should not contain '__answer' but does.\nOutput:\n{output}"
    )
    assert _is_structured_v2(output), (
        f"[O-V2-3] Output does not start with CONDITION: as expected for V2.\nOutput:\n{output}"
    )
