import pytest
from tests.evals.fixtures.loader import load_scenarios
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output
from agents.nodes.rca_analyzer import rca_analyzer


@pytest.mark.evals
@pytest.mark.parametrize("scenario", load_scenarios("rca"), ids=lambda s: s["id"])
async def test_rca_quality(scenario, eval_llm):
    state = build_state(scenario)
    result = await rca_analyzer(state)
    rule_id = scenario["rule"]["rule_id"]
    findings = result["parameter_records"][rule_id]["rca_findings"]
    assert findings, f"[{scenario['id']}] rca_analyzer returned empty rca_findings"
    score = await judge_output(findings, scenario["judge"], eval_llm, scenario_id=scenario["id"])
    assert score.passed, f"[{scenario['id']}] {score}"
