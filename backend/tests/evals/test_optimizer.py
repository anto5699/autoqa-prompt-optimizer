import pytest
from tests.evals.fixtures.loader import load_scenarios
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output
from agents.nodes.prompt_optimizer import prompt_optimizer


@pytest.mark.evals
@pytest.mark.parametrize("scenario", load_scenarios("optimizer"), ids=lambda s: s["id"])
async def test_optimizer_quality(scenario, eval_llm):
    state = build_state(scenario)
    result = await prompt_optimizer(state)
    rule_id = scenario["rule"]["rule_id"]
    new_description = result["parameter_records"][rule_id]["current_description"]
    assert new_description, f"[{scenario['id']}] prompt_optimizer returned empty description"
    score = await judge_output(new_description, scenario["judge"], eval_llm, scenario_id=scenario["id"])
    assert score.passed, f"[{scenario['id']}] {score}"
