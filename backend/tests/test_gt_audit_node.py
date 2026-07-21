"""Integration test: run the real pre_flight_gt_audit node with a stubbed LLM, then the
real resume/relabel path — verifies node wiring, question payload, and non-destructive overlay."""

import asyncio
from unittest.mock import patch

from agents.nodes.ambiguity_detection import _apply_gt_relabels
from agents.nodes import pre_flight_gt_audit as node


class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    """Branches on the system prompt: judge calls return per-conversation verdicts (keyed by a
    token embedded in the transcript); synthesis calls return the fixed 5-field text."""
    model_name = "fake-model"

    async def ainvoke(self, messages):
        system = messages[0].content
        human = messages[1].content
        if "ground-truth auditor" in system:  # judge call
            if "ADMIN_CALL" in human:      # calm admin → both metrics NA (trigger absent)
                verdicts = [
                    {"rule_id": "Compassion", "trigger_present": False, "answer_met": None,
                     "reason": "neutral admin, no distress"},
                    {"rule_id": "V's & C's", "trigger_present": False, "answer_met": None,
                     "reason": "no complaint intensity"},
                ]
            elif "DISTRESS_CALL" in human:  # genuine distress → Compassion Yes (trigger + met)
                verdicts = [
                    {"rule_id": "Compassion", "trigger_present": True, "answer_met": True,
                     "reason": "explicit distress expressed, agent responded with empathy"},
                    {"rule_id": "V's & C's", "trigger_present": False, "answer_met": None,
                     "reason": "no complaint"},
                ]
            elif "V2_UNMET_CALL" in human:  # V2 rule → CONDITION not met → NA
                verdicts = [
                    {"rule_id": "Greeting", "exception_present": False,
                     "prohibited_observed": False, "condition_met": False,
                     "expected_behavior_met": None, "reason": "condition never triggered"},
                ]
            else:                           # COMPLAINT_CALL → V's & C's in scope, not adhered
                verdicts = [
                    {"rule_id": "Compassion", "trigger_present": False, "answer_met": None,
                     "reason": "no emotional signal"},
                    {"rule_id": "V's & C's", "trigger_present": True, "answer_met": False,
                     "reason": "explicit complaint, not resolved"},
                ]
            import json
            return _FakeMsg(json.dumps(verdicts))
        # synthesis call
        return _FakeMsg(
            "Gap type: NO_GAP\n\n"
            "What the description evaluates: definition\n"
            "What GT data rewards: definition\n\n"
            "Alignment gaps:\n• None.\n\n"
            "Revised optimization strategy:\nNo changes needed."
        )


def _conv(cid, token):
    return {"conversation_id": cid, "transcript": [{"speaker": "customer", "msg": token}]}


def _build_state():
    return {
        "session_id": "test-audit",
        "rules": [
            {"rule_id": "Compassion", "rule_type": "dynamic",
             "description": "Agent showed compassion", "trigger_description": "Customer in distress"},
            {"rule_id": "V's & C's", "rule_type": "dynamic",
             "description": "Agent handled complaint", "trigger_description": "Explicit complaint present"},
            {"rule_id": "Greeting", "rule_type": "answer", "version": "v2",
             "description": "CONDITION: Customer calls in.\nEXPECTED BEHAVIOR:\n  - Agent greets by name.\nEXCEPTION: None."},
        ],
        "conversations": [
            _conv("c-over-1111", "ADMIN_CALL"),      # Compassion GT=Yes → should be NA (flag)
            _conv("c-keep-2222", "DISTRESS_CALL"),   # Compassion GT=Yes → should be Yes (ok)
            _conv("c-undr-3333", "COMPLAINT_CALL"),  # V's & C's GT=NA → should be No (flag)
            _conv("c-v2un-4444", "V2_UNMET_CALL"),   # Greeting (V2) GT=No → should be NA (flag)
        ],
        "ground_truth_map": {
            "c-over-1111": {"Compassion": "Yes", "V's & C's": "NA", "Greeting": "NA"},
            "c-keep-2222": {"Compassion": "Yes", "V's & C's": "NA", "Greeting": "NA"},
            "c-undr-3333": {"Compassion": "NA", "V's & C's": "NA", "Greeting": "NA"},
            "c-v2un-4444": {"Compassion": "NA", "V's & C's": "NA", "Greeting": "No"},
        },
        "llm_config": {},
        "pivot_asked_rule_ids": [],
    }


def test_pre_flight_gt_audit_node_end_to_end():
    state = _build_state()
    with patch.object(node, "get_llm", return_value=_FakeLLM()):
        result = asyncio.run(node.pre_flight_gt_audit(state))

    cases = result["pre_audit_cases"]
    # Compassion: only the admin call flagged (Yes → NA); the distress call matches and is not flagged
    comp = cases["Compassion"]
    assert [c["conversation_id"] for c in comp] == ["c-over-1111"]
    assert comp[0]["current_gt"] == "Yes" and comp[0]["should_be"] == "NA"
    # V's & C's: the complaint call flagged (NA → No)
    vc = cases["V's & C's"]
    assert [c["conversation_id"] for c in vc] == ["c-undr-3333"]
    assert vc[0]["current_gt"] == "NA" and vc[0]["should_be"] == "No"

    # Greeting (V2 unified rule): CONDITION not met → NA, disagrees with recorded GT=No (flag)
    greeting = cases["Greeting"]
    assert [c["conversation_id"] for c in greeting] == ["c-v2un-4444"]
    assert greeting[0]["current_gt"] == "No" and greeting[0]["should_be"] == "NA"

    # gt_relabel questions generated per flagged rule, each carrying its cases
    relabel_qs = [q for q in result["clarifying_questions"] if q.get("question_type") == "gt_relabel"]
    assert {q["parameter_name"] for q in relabel_qs} == {"Compassion", "V's & C's", "Greeting"}
    for q in relabel_qs:
        assert q["cases"] and q["flagged_count"] == len(q["cases"])
        assert q["metric_display_name"]

    # Feed the real questions through the resume path, accepting both → corrected GT overlay
    update = _apply_gt_relabels(
        {"ground_truth_map": state["ground_truth_map"]},
        relabel_qs,
        {q["question_id"]: "Yes" for q in relabel_qs},
    )
    corrected = update["ground_truth_map"]
    assert corrected["c-over-1111"]["Compassion"] == "NA"
    assert corrected["c-undr-3333"]["V's & C's"] == "No"
    # untouched + original preserved
    assert corrected["c-keep-2222"]["Compassion"] == "Yes"
    assert state["ground_truth_map"]["c-over-1111"]["Compassion"] == "Yes"
