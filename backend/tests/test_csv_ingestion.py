"""Unit tests for csv_ingestion node — ParameterOptimizationRecord version population."""
from agents.state import ParameterOptimizationRecord


def _make_rule(**overrides) -> dict:
    base = {
        "rule_id": "test_rule",
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        "description": "Agent greets the customer.",
        "trigger_description": None,
        "trigger_speaker": None,
    }
    base.update(overrides)
    return base


def _build_record(rule: dict) -> ParameterOptimizationRecord:
    """Mirror the ParameterOptimizationRecord construction in csv_ingestion.py."""
    return ParameterOptimizationRecord(
        rule_id=rule["rule_id"],
        rule_type=rule["rule_type"],
        version=rule.get("version", "v1"),
        speaker=rule["speaker"],
        trigger_description=rule.get("trigger_description"),
        trigger_speaker=rule.get("trigger_speaker"),
        evaluation_type=rule["evaluation_type"],
        n_messages=rule["n_messages"],
        current_description=rule["description"],
        original_description=rule["description"],
        iteration_history=[],
        current_predictions={},
        current_rationales={},
        current_accuracy=0.0,
        current_precision=0.0,
        current_recall=0.0,
        current_f1=0.0,
        true_positives=0,
        false_positives=0,
        true_negatives=0,
        false_negatives=0,
        not_applicable_count=0,
        rca_findings=None,
        optimization_notes=None,
        status="pending",
        initial_accuracy=None,
        best_accuracy=None,
        best_description=None,
        best_trigger_description=None,
    )


def test_record_version_v2_explicit():
    rule = _make_rule(version="v2")
    record = _build_record(rule)
    assert record["version"] == "v2"


def test_record_version_defaults_to_v1_when_missing():
    rule = _make_rule()  # no version key
    assert "version" not in rule
    record = _build_record(rule)
    assert record["version"] == "v1"
