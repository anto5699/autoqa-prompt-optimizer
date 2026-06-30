import pytest
from tests.evals.fixtures.loader import load_scenarios
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output
from agents.nodes.gt_alignment_audit import gt_alignment_audit


@pytest.mark.evals
@pytest.mark.parametrize("scenario", load_scenarios("alignment"), ids=lambda s: s["id"])
async def test_alignment_quality(scenario, eval_llm):
    state = build_state(scenario)
    result = await gt_alignment_audit(state)
    rule_id = scenario["rule"]["rule_id"]
    assert result, f"[{scenario['id']}] gt_alignment_audit returned empty dict (rule not stagnant?)"
    audit = result["parameter_records"][rule_id]["alignment_audit"]
    assert audit, f"[{scenario['id']}] gt_alignment_audit returned empty alignment_audit"
    score = await judge_output(audit, scenario["judge"], eval_llm, scenario_id=scenario["id"])
    assert score.passed, f"[{scenario['id']}] {score}"
