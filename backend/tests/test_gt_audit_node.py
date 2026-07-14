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
            if "ADMIN_CALL" in human:      # calm admin → both metrics NA
                verdicts = [
                    {"rule_id": "Compassion", "should_be": "NA", "reason": "neutral admin, no distress"},
                    {"rule_id": "V's & C's", "should_be": "NA", "reason": "no complaint intensity"},
                ]
            elif "DISTRESS_CALL" in human:  # genuine distress → Compassion Yes
                verdicts = [
                    {"rule_id": "Compassion", "should_be": "Yes", "reason": "explicit distress expressed"},
                    {"rule_id": "V's & C's", "should_be": "NA", "reason": "no complaint"},
                ]
            else:                           # COMPLAINT_CALL → V's & C's in scope, not adhered
                verdicts = [
                    {"rule_id": "Compassion", "should_be": "NA", "reason": "no emotional signal"},
                    {"rule_id": "V's & C's", "should_be": "No", "reason": "explicit complaint, not resolved"},
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
        ],
        "conversations": [
            _conv("c-over-1111", "ADMIN_CALL"),      # Compassion GT=Yes → should be NA (flag)
            _conv("c-keep-2222", "DISTRESS_CALL"),   # Compassion GT=Yes → should be Yes (ok)
            _conv("c-undr-3333", "COMPLAINT_CALL"),  # V's & C's GT=NA → should be No (flag)
        ],
        "ground_truth_map": {
            "c-over-1111": {"Compassion": "Yes", "V's & C's": "NA"},
            "c-keep-2222": {"Compassion": "Yes", "V's & C's": "NA"},
            "c-undr-3333": {"Compassion": "NA", "V's & C's": "NA"},
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

    # gt_relabel questions generated per flagged rule, each carrying its cases
    relabel_qs = [q for q in result["clarifying_questions"] if q.get("question_type") == "gt_relabel"]
    assert {q["parameter_name"] for q in relabel_qs} == {"Compassion", "V's & C's"}
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
