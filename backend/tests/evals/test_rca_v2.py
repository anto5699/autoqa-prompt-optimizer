"""V2 agent evals for the rca_analyzer node.

Scenarios
---------
R-V2-1  V2 FP framed in EXPECTED BEHAVIOR / CONDITION terms
R-V2-2  V2 NA misprediction identified as false_na_prediction; RCA addresses EXCEPTION over-triggering
R-V2-3  V2 FN framed in EXPECTED BEHAVIOR terms
"""
import pytest

from agents.nodes.rca_analyzer import rca_analyzer
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output


_V2_ESCALATION_DESC = (
    "CONDITION: Always.\n"
    "EXPECTED BEHAVIOR:\n"
    "  - Agent explicitly offers to escalate to a supervisor when the customer expresses dissatisfaction.\n"
    "PROHIBITED: Offering escalation on routine calls where no dissatisfaction is present.\n"
    "EXCEPTION: Customer proactively requests escalation without expressing dissatisfaction."
)

_V2_GREETING_DESC = (
    "CONDITION: Always.\n"
    "EXPECTED BEHAVIOR:\n"
    "  - Agent greets the customer at the start of the call.\n"
    "EXCEPTION: Customer immediately disconnects before agent can respond."
)


def _make_v2_state(rule_id: str, description: str, conversations: list, scene_id: str) -> dict:
    return {
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
        "conversations": conversations,
    }


# ---------------------------------------------------------------------------
# R-V2-1: V2 FP framed in EXPECTED BEHAVIOR / CONDITION terms
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_r_v2_1_fp_framed_in_v2_terms(eval_llm):
    """RCA for V2 FPs mentions EXPECTED BEHAVIOR or CONDITION; not PASS_CRITERIA or trigger rule."""
    conversations = [
        {
            "id": "c1",
            "transcript": [
                {"speaker": "customer", "msg": "I need to update my address."},
                {"speaker": "agent", "msg": "Of course! I can help with that."},
            ],
            "ground_truth": "No",
            "prediction": "Yes",
        },
        {
            "id": "c2",
            "transcript": [
                {"speaker": "customer", "msg": "What are your business hours?"},
                {"speaker": "agent", "msg": "We are open Monday to Friday, 8am to 8pm."},
            ],
            "ground_truth": "No",
            "prediction": "Yes",
        },
        {
            "id": "c3",
            "transcript": [
                {"speaker": "customer", "msg": "This is the third time I've called about this!"},
                {"speaker": "agent", "msg": "I sincerely apologise. Would you like me to transfer you to a supervisor?"},
            ],
            "ground_truth": "Yes",
            "prediction": "Yes",
        },
    ]
    scenario = _make_v2_state("EscalationOfferV2", _V2_ESCALATION_DESC, conversations, "r-v2-1")
    state = build_state(scenario)
    result = await rca_analyzer(state)

    findings = result["parameter_records"]["EscalationOfferV2"]["rca_findings"]
    assert findings, "[R-V2-1] rca_analyzer returned empty rca_findings"

    judge_config = {
        "dimensions": [
            {
                "id": "v2_terminology",
                "weight": 0.40,
                "prompt": (
                    "RCA output:\n{output}\n\n"
                    "Does the RCA reference at least one V2 concept by name — "
                    "e.g., 'CONDITION', 'EXPECTED BEHAVIOR', 'PROHIBITED', or 'EXCEPTION' — "
                    "anywhere in the text (even once, including in a recommendation)? "
                    "Score 1.0 if any V2 term appears; 0.7 if the RCA describes the V2 concept "
                    "without the exact label (e.g., 'when dissatisfaction is expressed' maps to CONDITION); "
                    "0.0 only if it uses V1 labels like 'PASS_CRITERIA' instead."
                ),
            },
            {
                "id": "no_v1_only_terminology",
                "weight": 0.20,
                "prompt": (
                    "RCA output:\n{output}\n\n"
                    "Does the RCA avoid using V1-specific terminology such as 'PASS_CRITERIA', "
                    "'METRIC_NAME', or 'PASS_LOGIC'? "
                    "(Note: the word 'trigger' used as a verb is acceptable; 'trigger rule' as a "
                    "V1 concept label is not.)"
                ),
            },
            {
                "id": "root_cause_accuracy",
                "weight": 0.40,
                "prompt": (
                    "Context: The escalation rule fires on ALL calls (c1, c2 routine; c3 correct positive). "
                    "The CONDITION or scope is too broad.\n"
                    "RCA output:\n{output}\n\n"
                    "Does the RCA correctly identify that the rule fires on routine calls where no "
                    "dissatisfaction exists, and recommend restricting the scope/CONDITION?"
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(findings, judge_config, eval_llm, scenario_id="r-v2-1")
    assert score.passed, f"[R-V2-1] {score}"


# ---------------------------------------------------------------------------
# R-V2-2: V2 NA misprediction identified; RCA addresses EXCEPTION over-triggering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_r_v2_2_false_na_rca(eval_llm):
    """RCA for V2 NA mispredictions addresses EXCEPTION over-triggering."""
    conversations = [
        {
            "id": "c1",
            "transcript": [
                {"speaker": "agent", "msg": "Hello, thank you for calling. How can I help you?"},
                {"speaker": "customer", "msg": "Hi, I have a question about my bill."},
            ],
            "ground_truth": "Yes",
            "prediction": "NA",
        },
        {
            "id": "c2",
            "transcript": [
                {"speaker": "agent", "msg": "Good morning! How may I assist you today?"},
                {"speaker": "customer", "msg": "I'd like to update my address."},
            ],
            "ground_truth": "Yes",
            "prediction": "NA",
        },
        {
            "id": "c3",
            "transcript": [
                {"speaker": "agent", "msg": "Hi there, thanks for calling customer support."},
                {"speaker": "customer", "msg": "I need help with my subscription."},
            ],
            "ground_truth": "Yes",
            "prediction": "Yes",
        },
    ]
    scenario = _make_v2_state("AgentGreetingNA", _V2_GREETING_DESC, conversations, "r-v2-2")
    state = build_state(scenario)
    result = await rca_analyzer(state)

    findings = result["parameter_records"]["AgentGreetingNA"]["rca_findings"]
    assert findings, "[R-V2-2] rca_analyzer returned empty rca_findings"

    judge_config = {
        "dimensions": [
            {
                "id": "exception_over_triggering",
                "weight": 0.60,
                "prompt": (
                    "Context: 2 conversations predicted NA but GT=Yes, meaning the EXCEPTION "
                    "fired when it should not have.\n"
                    "RCA output:\n{output}\n\n"
                    "Does the RCA identify that the EXCEPTION clause is over-triggering (firing when "
                    "it should not), or that the CONDITION is under-matching normal conversations? "
                    "Score 1.0 if either issue is clearly identified."
                ),
            },
            {
                "id": "actionability",
                "weight": 0.40,
                "prompt": (
                    "RCA output:\n{output}\n\n"
                    "Does the RCA recommend tightening the EXCEPTION definition or clarifying "
                    "the CONDITION to prevent over-classification as Not Applicable?"
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(findings, judge_config, eval_llm, scenario_id="r-v2-2")
    assert score.passed, f"[R-V2-2] {score}"


# ---------------------------------------------------------------------------
# R-V2-3: V2 FN framed in EXPECTED BEHAVIOR terms
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_r_v2_3_fn_framed_in_expected_behavior(eval_llm):
    """RCA for V2 FNs focuses on EXPECTED BEHAVIOR being too strict or ambiguous."""
    conversations = [
        {
            "id": "c1",
            "transcript": [
                {"speaker": "agent", "msg": "Hi, you've reached customer support. I'm Sam."},
                {"speaker": "customer", "msg": "Hello, I need help."},
            ],
            "ground_truth": "Yes",
            "prediction": "No",
        },
        {
            "id": "c2",
            "transcript": [
                {"speaker": "agent", "msg": "Welcome to support. How can I help you today?"},
                {"speaker": "customer", "msg": "Hi there."},
            ],
            "ground_truth": "Yes",
            "prediction": "No",
        },
        {
            "id": "c3",
            "transcript": [
                {"speaker": "agent", "msg": "Thank you for calling. My name is Jordan, how can I assist?"},
                {"speaker": "customer", "msg": "I have a billing question."},
            ],
            "ground_truth": "Yes",
            "prediction": "No",
        },
    ]
    scenario = _make_v2_state("AgentGreetingFN", _V2_GREETING_DESC, conversations, "r-v2-3")
    state = build_state(scenario)
    result = await rca_analyzer(state)

    findings = result["parameter_records"]["AgentGreetingFN"]["rca_findings"]
    assert findings, "[R-V2-3] rca_analyzer returned empty rca_findings"

    judge_config = {
        "dimensions": [
            {
                "id": "expected_behavior_focus",
                "weight": 0.60,
                "prompt": (
                    "Context: agents in all 3 conversations said greetings but were predicted No (false negatives). "
                    "RCA output:\n{output}\n\n"
                    "Does the RCA suggest that EXPECTED BEHAVIOR is too strict (e.g., requires specific phrasing) "
                    "or too ambiguous (e.g., unclear what counts as a greeting), causing valid greetings to be missed?"
                ),
            },
            {
                "id": "actionable_suggestion",
                "weight": 0.40,
                "prompt": (
                    "RCA output:\n{output}\n\n"
                    "Does the RCA provide an actionable suggestion that specifically targets the "
                    "EXPECTED BEHAVIOR wording to reduce false negatives?"
                ),
            },
        ],
        "pass_threshold": 0.70,
    }

    score = await judge_output(findings, judge_config, eval_llm, scenario_id="r-v2-3")
    assert score.passed, f"[R-V2-3] {score}"
