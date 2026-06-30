import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.evals.fixtures.state_factory import build_state

_SCENARIO = {
    "id": "test-001",
    "node": "rca_analyzer",
    "rule": {"rule_id": "Greeting", "description": "Agent greets customer", "rule_type": "answer", "speaker": "Agent", "evaluation_type": "entire", "n_messages": -1},
    "conversations": [
        {"id": "c1", "transcript": [], "ground_truth": "Yes", "prediction": "No"},   # FN
        {"id": "c2", "transcript": [], "ground_truth": "No",  "prediction": "No"},   # TN
        {"id": "c3", "transcript": [], "ground_truth": "Yes", "prediction": "Yes"},  # TP
    ],
    "judge": {"dimensions": [], "pass_threshold": 0.70},
}

def test_confusion_matrix():
    state = build_state(_SCENARIO)
    rec = state["parameter_records"]["Greeting"]
    assert rec["true_positives"] == 1
    assert rec["false_negatives"] == 1
    assert rec["true_negatives"] == 1
    assert rec["false_positives"] == 0

def test_accuracy():
    state = build_state(_SCENARIO)
    rec = state["parameter_records"]["Greeting"]
    assert abs(rec["current_accuracy"] - 2/3) < 0.01

def test_parameters_below_target_contains_rule():
    state = build_state(_SCENARIO)
    assert "Greeting" in state["parameters_below_target"]

def test_skip_setup_is_true():
    state = build_state(_SCENARIO)
    assert state["skip_setup"] is True
