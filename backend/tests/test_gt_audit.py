"""Unit tests for the pre-flight ground-truth audit: diff/aggregate + non-destructive relabel."""

from agents.nodes.ambiguity_detection import _apply_gt_relabels
from agents.nodes.pre_flight_gt_audit import _derive_should_be_v2, _normalize_label, diff_cases


def test_derive_should_be_v2_exception_wins_over_everything():
    obj = {
        "exception_present": True, "prohibited_observed": True,
        "condition_met": True, "expected_behavior_met": True,
    }
    assert _derive_should_be_v2(obj) == "NA"


def test_derive_should_be_v2_prohibited_beats_condition_not_met():
    # Mirrors config.py's DECISION LOGIC order: PROHIBITED is checked before CONDITION.
    obj = {
        "exception_present": False, "prohibited_observed": True,
        "condition_met": False, "expected_behavior_met": None,
    }
    assert _derive_should_be_v2(obj) == "No"


def test_derive_should_be_v2_condition_not_met_is_na():
    obj = {
        "exception_present": False, "prohibited_observed": False,
        "condition_met": False, "expected_behavior_met": None,
    }
    assert _derive_should_be_v2(obj) == "NA"


def test_derive_should_be_v2_condition_met_expected_behavior_yes():
    obj = {
        "exception_present": False, "prohibited_observed": False,
        "condition_met": True, "expected_behavior_met": True,
    }
    assert _derive_should_be_v2(obj) == "Yes"


def test_derive_should_be_v2_condition_met_expected_behavior_no():
    obj = {
        "exception_present": False, "prohibited_observed": False,
        "condition_met": True, "expected_behavior_met": False,
    }
    assert _derive_should_be_v2(obj) == "No"


def test_derive_should_be_v2_missing_prohibited_defaults_to_not_observed():
    # No PROHIBITED section in the rule → model reports null, must not block derivation.
    obj = {
        "exception_present": False, "prohibited_observed": None,
        "condition_met": True, "expected_behavior_met": True,
    }
    assert _derive_should_be_v2(obj) == "Yes"


def test_derive_should_be_v2_missing_required_fields_return_none():
    assert _derive_should_be_v2({"exception_present": None}) is None
    assert _derive_should_be_v2({"exception_present": False, "condition_met": None}) is None
    assert _derive_should_be_v2({
        "exception_present": False, "condition_met": True, "expected_behavior_met": None,
    }) is None


def test_normalize_label_variants():
    assert _normalize_label("Yes") == "Yes"
    assert _normalize_label("adhered") == "Yes"
    assert _normalize_label("NO") == "No"
    assert _normalize_label("Not Adhered") == "No"
    assert _normalize_label("n/a") == "NA"
    assert _normalize_label("Not Applicable") == "NA"
    assert _normalize_label("") == "NA"
    assert _normalize_label(None) == "NA"
    # Unknown values default to NA rather than raising
    assert _normalize_label("maybe") == "NA"


def test_diff_cases_flags_only_disagreements():
    conv_verdicts = [
        ("c-1", {"Compassion": {"should_be": "NA", "reason": "neutral admin call"}}),   # GT=Yes → flag
        ("c-2", {"Compassion": {"should_be": "Yes", "reason": "matches"}}),             # GT=Yes → ok
        ("c-3", {"Compassion": {"should_be": "No", "reason": "under-labelled"}}),       # GT=NA → flag
        ("c-4", {"Unknown": {"should_be": "No", "reason": "rule not tracked"}}),        # unknown rule → ignored
    ]
    ground_truth_map = {
        "c-1": {"Compassion": "Yes"},
        "c-2": {"Compassion": "Yes"},
        "c-3": {"Compassion": "NA"},
        "c-4": {"Compassion": "Yes"},   # c-4 has no Compassion verdict → not flagged
    }
    cases = diff_cases(conv_verdicts, ground_truth_map, ["Compassion"])
    flagged = cases["Compassion"]
    assert {c["conversation_id"] for c in flagged} == {"c-1", "c-3"}
    by_id = {c["conversation_id"]: c for c in flagged}
    assert by_id["c-1"]["current_gt"] == "Yes" and by_id["c-1"]["should_be"] == "NA"
    assert by_id["c-3"]["current_gt"] == "NA" and by_id["c-3"]["should_be"] == "No"
    assert by_id["c-1"]["reason"] == "neutral admin call"


def test_diff_cases_skips_missing_gt():
    conv_verdicts = [("c-1", {"Compassion": {"should_be": "NA"}})]
    ground_truth_map = {"c-1": {}}  # no Compassion label → skipped, not flagged
    cases = diff_cases(conv_verdicts, ground_truth_map, ["Compassion"])
    assert cases["Compassion"] == []


def _relabel_q(question_id, rule_id, cases):
    return {
        "question_id": question_id,
        "parameter_name": rule_id,
        "question_type": "gt_relabel",
        "cases": cases,
    }


def test_apply_gt_relabels_non_destructive_and_scoped():
    original = {
        "c-1": {"Compassion": "Yes", "V's & C's": "Yes"},
        "c-2": {"Compassion": "Yes", "V's & C's": "NA"},
        "c-3": {"Compassion": "No", "V's & C's": "Yes"},
    }
    state = {"ground_truth_map": original}

    questions = [
        _relabel_q("q1", "Compassion", [
            {"conversation_id": "c-1", "current_gt": "Yes", "should_be": "NA", "reason": "r"},
            {"conversation_id": "c-2", "current_gt": "Yes", "should_be": "NA", "reason": "r"},
        ]),
        # Not accepted → must NOT be applied
        _relabel_q("q2", "V's & C's", [
            {"conversation_id": "c-1", "current_gt": "Yes", "should_be": "NA", "reason": "r"},
        ]),
    ]
    answers = {"q1": "Yes", "q2": "No"}

    update = _apply_gt_relabels(state, questions, answers)

    corrected = update["ground_truth_map"]
    # Accepted rule corrections applied
    assert corrected["c-1"]["Compassion"] == "NA"
    assert corrected["c-2"]["Compassion"] == "NA"
    # Rejected rule untouched
    assert corrected["c-1"]["V's & C's"] == "Yes"
    # Unrelated cells untouched
    assert corrected["c-3"]["Compassion"] == "No"
    # Original snapshot preserved and NOT mutated (non-destructive)
    assert update["ground_truth_map_original"]["c-1"]["Compassion"] == "Yes"
    assert original["c-1"]["Compassion"] == "Yes"
    assert corrected is not original
    # Corrections recorded with from/to
    applied = update["gt_corrections_applied"]["Compassion"]
    assert {a["conversation_id"] for a in applied} == {"c-1", "c-2"}
    assert applied[0]["from_gt"] == "Yes" and applied[0]["to_gt"] == "NA"


def test_apply_gt_relabels_noop_when_nothing_accepted():
    state = {"ground_truth_map": {"c-1": {"Compassion": "Yes"}}}
    questions = [_relabel_q("q1", "Compassion", [
        {"conversation_id": "c-1", "current_gt": "Yes", "should_be": "NA", "reason": "r"},
    ])]
    assert _apply_gt_relabels(state, questions, {"q1": "No"}) == {}


def test_apply_gt_relabels_noop_when_correction_is_a_no_op():
    # should_be already equals current GT → nothing to change
    state = {"ground_truth_map": {"c-1": {"Compassion": "Yes"}}}
    questions = [_relabel_q("q1", "Compassion", [
        {"conversation_id": "c-1", "current_gt": "Yes", "should_be": "Yes", "reason": "r"},
    ])]
    assert _apply_gt_relabels(state, questions, {"q1": "Yes"}) == {}
