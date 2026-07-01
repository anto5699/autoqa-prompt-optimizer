import pytest
from tests.evals.fixtures.loader import load_scenarios
from tests.evals.fixtures.state_factory import build_state
from tests.evals.judge.runner import judge_output
from agents.nodes.mid_loop_clarification import mid_loop_clarification
from utils.session_store import session_store


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

    # For stagnant rules the node writes questions to session_store and then calls interrupt().
    # In test context interrupt() raises RuntimeError ("Called get_config outside of a runnable
    # context") rather than GraphInterrupt, so extract questions from session_store instead.
    # session_store.update() is a no-op for uninitialised sessions, so seed it first.
    session_id = state["session_id"]
    session_store.add(session_id, {"current_phase": "evaluating"})
    questions_text = ""
    try:
        await mid_loop_clarification(state)
        pytest.fail(f"[{scenario['id']}] Expected interrupt but node returned without one")
    except Exception as exc:
        # Primary: read from session_store — always written before interrupt() is called
        session_data = session_store.get(session_id) or {}
        stored_questions = session_data.get("clarifying_questions", [])
        if stored_questions:
            questions_text = "\n".join(
                q.get("question_text", str(q)) if isinstance(q, dict) else q.question_text
                for q in stored_questions
            )
        if not questions_text:
            # Fallback: extract from a proper GraphInterrupt exception value
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
