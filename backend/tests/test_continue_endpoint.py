import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch


def _make_live_state(below_target=("rule1",)):
    return {
        "session_id": "orig-session",
        "system_prompt": "sys",
        "language": "en",
        "llm_config": {},
        "conversations": [{"id": "c1", "messages": []}],
        "rules": [
            {"rule_id": "rule1", "rule_type": "answer", "speaker": "agent",
             "evaluation_type": "entire", "n_messages": 0, "description": "desc"},
        ],
        "ground_truth_map": {"c1": {"rule1": "Yes"}},
        "excluded_rules": [],
        "accuracy_target": 0.9,
        "parameters_below_target": list(below_target),
        "parameters_meeting_target": [],
        "parameter_records": {
            "rule1": {
                "rule_id": "rule1", "rule_type": "answer", "speaker": "agent",
                "evaluation_type": "entire", "n_messages": 0,
                "current_description": "desc",
                "iteration_history": [{"iteration": 0, "accuracy": 0.5}],
                "current_predictions": {"c1": "No"},
                "current_accuracy": 0.5, "current_precision": 0.0,
                "current_recall": 0.0, "current_f1": 0.0,
                "true_positives": 0, "false_positives": 0,
                "true_negatives": 0, "false_negatives": 1,
                "not_applicable_count": 0,
                "rca_findings": "Model misunderstood phrasing.",
                "optimization_notes": None,
                "status": "max_iterations_reached",
                "initial_accuracy": 0.4, "best_accuracy": 0.5,
                "best_description": "desc",
            }
        },
        "progress_log": [],
    }


def test_continue_session_returns_new_session_id():
    from main import app
    from utils.session_store import session_store
    from agents.graph import graph_app

    session_store.add("orig-session", {
        "session_id": "orig-session",
        "current_phase": "complete",
        "optimization_complete": True,
        "current_iteration": 5,
        "clarifying_questions": [],
        "parameter_summary": {},
        "progress_log": [],
        "_metric_names": ["rule1"],
        "_na_detected_parameters": [],
        "_conversations": [],
        "_ground_truth_map": {},
        "_excluded_rules": [],
        "_max_iterations": 5,
        "_accuracy_target": 0.9,
        "_language": "en",
        "_llm_config": {},
    })

    mock_state = MagicMock()
    mock_state.values = _make_live_state()
    mock_state.next = []

    with patch.object(graph_app, "get_state", return_value=mock_state), \
         patch("api.routes.sessions.asyncio.create_task"):
        client = TestClient(app)
        resp = client.post("/api/sessions/orig-session/continue", json={"additional_iterations": 3})

    assert resp.status_code == 201
    data = resp.json()
    assert "new_session_id" in data
    assert data["new_session_id"] != "orig-session"
    assert "rule1" in data["parameters_continuing"]

    session_store.delete("orig-session")
    if data.get("new_session_id"):
        session_store.delete(data["new_session_id"])


def test_continue_session_404_for_unknown_session():
    from main import app
    client = TestClient(app)
    resp = client.post("/api/sessions/nonexistent/continue", json={"additional_iterations": 3})
    assert resp.status_code == 404


def test_continue_session_409_when_not_complete():
    from main import app
    from utils.session_store import session_store

    session_store.add("in-progress-session", {
        "session_id": "in-progress-session",
        "current_phase": "evaluating",
        "optimization_complete": False,
    })

    client = TestClient(app)
    resp = client.post("/api/sessions/in-progress-session/continue", json={"additional_iterations": 3})
    assert resp.status_code == 409

    session_store.delete("in-progress-session")


def test_continue_session_409_when_all_converged():
    from main import app
    from utils.session_store import session_store
    from agents.graph import graph_app

    session_store.add("all-converged", {
        "session_id": "all-converged",
        "current_phase": "complete",
        "optimization_complete": True,
    })

    mock_state = MagicMock()
    mock_state.values = _make_live_state(below_target=[])

    with patch.object(graph_app, "get_state", return_value=mock_state):
        client = TestClient(app)
        resp = client.post("/api/sessions/all-converged/continue", json={"additional_iterations": 3})

    assert resp.status_code == 409

    session_store.delete("all-converged")


def test_continue_session_400_for_invalid_iterations():
    from main import app
    from utils.session_store import session_store

    session_store.add("s1", {"session_id": "s1", "current_phase": "complete"})
    client = TestClient(app)
    resp = client.post("/api/sessions/s1/continue", json={"additional_iterations": 99})
    assert resp.status_code == 400
    session_store.delete("s1")
