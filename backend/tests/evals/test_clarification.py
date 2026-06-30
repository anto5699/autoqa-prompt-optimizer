import pytest
from tests.evals.fixtures.loader import load_scenarios
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output
from agents.nodes.mid_loop_clarification import mid_loop_clarification


@pytest.mark.evals
@pytest.mark.parametrize("scenario", load_scenarios("clarification"), ids=lambda s: s["id"])
async def test_clarification_quality(scenario, eval_llm):
    state = build_state(scenario)
    expect_interrupt = scenario.get("expect_interrupt", True)

    if not expect_interrupt:
        result = await mid_loop_clarification(state)
        # Node should return {} — no questions generated
        questions_output = str(result.get("clarifying_questions", []))
        score = await judge_output(questions_output, scenario["judge"], eval_llm, scenario_id=scenario["id"])
        assert score.passed, f"[{scenario['id']}] {score}"
        return

    # For stagnant rules the node calls interrupt() which raises NodeInterrupt
    questions_text = ""
    try:
        await mid_loop_clarification(state)
        pytest.fail(f"[{scenario['id']}] Expected interrupt but node returned without one")
    except Exception as exc:
        # NodeInterrupt.args[0] is a list of Interrupt objects with .value attribute
        try:
            interrupts = exc.args[0]
            value = interrupts[0].value if hasattr(interrupts[0], "value") else {}
            questions = value.get("clarifying_questions", [])
            questions_text = "\n".join(
                q.get("question_text", str(q)) if isinstance(q, dict) else q.question_text
                for q in questions
            )
        except Exception:
            questions_text = str(exc)

    assert questions_text, f"[{scenario['id']}] Could not extract question text from interrupt"
    score = await judge_output(questions_text, scenario["judge"], eval_llm, scenario_id=scenario["id"])
    assert score.passed, f"[{scenario['id']}] {score}"
