import json
import pytest
from tests.evals.fixtures.loader import load_scenarios
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output
from agents.graph import graph_app


@pytest.mark.evals
@pytest.mark.e2e
@pytest.mark.parametrize("scenario", load_scenarios("e2e"), ids=lambda s: s["id"])
async def test_e2e_quality(scenario, eval_llm):
    state = build_state(scenario)
    config = {"configurable": {"thread_id": f"eval-{scenario['id']}"}}
    result = await graph_app.ainvoke(state, config=config)

    summary = json.dumps({
        "optimization_complete": result.get("optimization_complete"),
        "current_iteration": result.get("current_iteration"),
        "final_report": result.get("final_report"),
        "parameter_records": {
            rule_id: {
                "status": rec.get("status"),
                "current_accuracy": rec.get("current_accuracy"),
                "iteration_history": [
                    {"iteration": h["iteration"], "accuracy": h["accuracy"]}
                    for h in rec.get("iteration_history", [])
                ],
            }
            for rule_id, rec in result.get("parameter_records", {}).items()
        },
    }, indent=2)

    score = await judge_output(summary, scenario["judge"], eval_llm, scenario_id=scenario["id"])
    assert score.passed, f"[{scenario['id']}] {score}"
