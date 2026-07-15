"""Deterministic unit tests for the GT-alignment accommodations (Changes 1–4).

All LLM-free: benchmarking/metrics/consensus are pure; the GT alignment audit's single LLM call
is monkeypatched. Confirms new behaviour triggers only on its narrow conditions and that defaults
preserve today's behaviour.
"""
import asyncio

import pytest

from agents.nodes.benchmarking import _iters_without_improvement, benchmarking
from agents.nodes.gt_alignment_audit import _no_progress
from agents.nodes.pre_flight_gt_audit import _consensus_verdicts, diff_cases
from config import settings
from utils.accuracy_metrics import compute_metrics, wilson_interval
from utils.session_store import session_store


def _hist(accs):
    return {"iteration_history": [{"accuracy": a} for a in accs]}


# ─────────────────── audit trigger: no-progress incl. oscillation ───────────────────

def test_no_progress_tight_flat():
    # spread < stagnation_spread over the window → stagnant
    assert _no_progress(_hist([0.5, 0.5, 0.5])) is True


def test_no_progress_oscillation_without_improvement():
    # not tight-flat (spread 0.08) but best (0.5) never beaten for >= window iterations
    assert _no_progress(_hist([0.5, 0.4, 0.45, 0.48])) is True


def test_no_progress_false_when_improving():
    assert _no_progress(_hist([0.5, 0.6, 0.7])) is False


def test_no_progress_false_with_short_history():
    assert _no_progress(_hist([0.5, 0.4])) is False


def test_no_progress_respects_disable_flag(monkeypatch):
    monkeypatch.setattr(settings, "audit_on_no_improvement", False)
    # oscillation no longer counts when disabled; tight-flat still does
    assert _no_progress(_hist([0.5, 0.4, 0.45, 0.48])) is False
    assert _no_progress(_hist([0.5, 0.5, 0.5])) is True


# ─────────────────── finalize: 5b clamp + CI denominator ───────────────────

def _finalize_record(rid, accuracy, status="max_iterations_reached"):
    return {
        "rule_id": rid, "rule_type": "dynamic", "version": "v1", "speaker": "agent",
        "trigger_description": "t", "evaluation_type": "entire", "n_messages": 0,
        "current_description": "desc", "original_description": "desc",
        "iteration_history": [{"iteration": 0, "accuracy": accuracy, "description": "desc"}],
        "current_predictions": {"c1": "Yes", "c2": "No", "c3": "NA", "c4": "NA", "c5": "NA"},
        "current_accuracy": accuracy, "current_precision": 0.0, "current_recall": 0.0,
        "current_f1": 0.0, "true_positives": 1, "false_positives": 0, "true_negatives": 1,
        "false_negatives": 0, "not_applicable_count": 3, "rca_findings": None,
        "optimization_notes": None, "status": status,
        "initial_accuracy": accuracy, "best_accuracy": accuracy, "best_description": "desc",
    }


def _finalize_state(records, pre_audit_cases):
    # gt: 2 evaluable (Yes/No) + 3 NA → evaluable_n = 2, n_total = 5
    gt = {"c1": {r: "Yes" for r in records}, "c2": {r: "No" for r in records},
          "c3": {r: "NA" for r in records}, "c4": {r: "NA" for r in records},
          "c5": {r: "NA" for r in records}}
    return {
        "session_id": "fin", "parameter_records": records,
        "parameters_below_target": [], "parameters_meeting_target": list(records),
        "current_iteration": 3, "accuracy_target": 0.9,
        "conversations": [{"id": c} for c in ("c1", "c2", "c3", "c4", "c5")],
        "ground_truth_map": gt, "pre_audit_cases": pre_audit_cases, "progress_log": [],
    }


def test_finalize_label_consistency_clamped_and_ci_on_evaluable_n():
    from agents.nodes.finalize import finalize

    rec = _finalize_record("r1", 0.5)
    # 4 flagged cases > evaluable_n (2) → unclamped score would be 1 - 4/2 = -1.0
    cases = [{"conversation_id": f"c{i}", "current_gt": "NA", "should_be": "Yes",
              "reason": "x", "confidence": 1.0} for i in range(4)]
    state = _finalize_state({"r1": rec}, {"r1": cases})
    report = asyncio.run(finalize(state))["final_report"]["parameters"]["r1"]

    assert report["evaluable_n"] == 2
    assert report["label_consistency_score"] == 0.0            # clamped, not negative
    # CI is on evaluable_n (2), NOT on n_total (5)
    assert report["accuracy_ci"] == wilson_interval(0.5, 2)
    assert report["accuracy_ci"] != wilson_interval(0.5, 5)


# ─────────────────────────── pure helpers ───────────────────────────

def test_iters_without_improvement():
    assert _iters_without_improvement([], 0.01) == 0
    assert _iters_without_improvement([{"accuracy": 0.5}], 0.01) == 0
    # flat run of 4 → 3 iterations since the (first) best
    assert _iters_without_improvement([{"accuracy": 0.5}] * 4, 0.01) == 3
    # last entry improves → 0
    assert _iters_without_improvement(
        [{"accuracy": 0.5}, {"accuracy": 0.5}, {"accuracy": 0.7}], 0.01
    ) == 0
    # tiny wobble below min_delta still counts as flat
    assert _iters_without_improvement(
        [{"accuracy": 0.50}, {"accuracy": 0.505}, {"accuracy": 0.505}], 0.01
    ) == 2


def test_compute_metrics_exposes_n_and_evaluable_n():
    m = compute_metrics(
        {"a": "Yes", "b": "No", "c": "NA"},
        {"a": {"r": "Yes"}, "b": {"r": "No"}, "c": {"r": "NA"}},
        "r",
    )
    assert m["n"] == 3            # all labelled conversations
    assert m["evaluable_n"] == 2  # Yes/No answer rows only


def test_wilson_interval():
    assert wilson_interval(0.8, 0) is None
    lo_small = wilson_interval(0.8, 5)
    lo_big = wilson_interval(0.8, 500)
    # tiny n → much wider interval than large n (the fragility signal for 5c)
    assert (lo_small["high"] - lo_small["low"]) > (lo_big["high"] - lo_big["low"])


# ─────────────────────────── Change 3: consensus ───────────────────────────

def test_consensus_single_run_is_unchanged_with_confidence_1():
    runs = [[("c1", {"r": {"should_be": "Yes", "reason": "x"}})]]
    out = _consensus_verdicts(runs, ["r"])
    assert out == [("c1", {"r": {"should_be": "Yes", "reason": "x", "confidence": 1.0}})]


def test_consensus_majority_vote_and_confidence():
    runs = [
        [("c1", {"r": {"should_be": "Yes", "reason": "a"}})],
        [("c1", {"r": {"should_be": "Yes", "reason": "b"}})],
        [("c1", {"r": {"should_be": "No", "reason": "c"}})],
    ]
    out = dict(_consensus_verdicts(runs, ["r"]))
    assert out["c1"]["r"]["should_be"] == "Yes"
    assert out["c1"]["r"]["confidence"] == pytest.approx(2 / 3, abs=1e-3)


def test_diff_cases_carries_confidence():
    verdicts = [("c1", {"r": {"should_be": "No", "reason": "z", "confidence": 0.67}})]
    cases = diff_cases(verdicts, {"c1": {"r": "Yes"}}, ["r"])
    assert cases["r"][0]["confidence"] == 0.67
    # default 1.0 when unset (single-judge parity)
    v2 = [("c1", {"r": {"should_be": "No", "reason": "z"}})]
    assert diff_cases(v2, {"c1": {"r": "Yes"}}, ["r"])["r"][0]["confidence"] == 1.0


# ─────────────────────────── Change 1: stall early-stop ───────────────────────────

def _flat_record(status="optimizing", audit_iteration=None, history_len=3, acc=0.5):
    # 2 conversations → accuracy 0.5 (TP=1, FP=1)
    return {
        "rule_id": "r1", "rule_type": "answer", "speaker": "Agent",
        "trigger_description": None, "trigger_speaker": None,
        "evaluation_type": "entire", "n_messages": 0,
        "current_description": "d", "current_predictions": {"c1": "Yes", "c2": "Yes"},
        "current_rationales": {}, "current_accuracy": acc,
        "current_precision": 0.0, "current_recall": 0.0, "current_f1": 0.0,
        "true_positives": 0, "false_positives": 0, "true_negatives": 0,
        "false_negatives": 0, "not_applicable_count": 0,
        "rca_findings": None, "optimization_notes": None, "status": status,
        "initial_accuracy": acc, "best_accuracy": acc, "best_description": "d",
        "best_trigger_description": None, "original_description": "d",
        "audit_iteration": audit_iteration,
        "iteration_history": [{"iteration": i, "accuracy": acc, "precision": 0.0,
                               "recall": 0.0, "f1": 0.0} for i in range(history_len)],
    }


def _bench_state(record, iteration=3):
    gt = {"c1": {"r1": "Yes"}, "c2": {"r1": "No"}}  # → accuracy 0.5, below 0.9 target
    return {
        "session_id": "stall-test", "parameter_records": {"r1": record},
        "ground_truth_map": gt, "accuracy_target": 0.9, "current_iteration": iteration,
        "parameters_meeting_target": [], "parameters_below_target": [], "progress_log": [],
    }


def test_stall_fires_when_flat_and_audited():
    session_store.add("stall-test", {"progress_log": []})
    rec = _flat_record(audit_iteration=1, history_len=3)  # +1 appended → 4 flat → iters_flat=3
    result = asyncio.run(benchmarking(_bench_state(rec)))
    r = result["parameter_records"]["r1"]
    assert r["status"] == "stalled"
    assert r["stop_reason"] == "stalled_no_progress"
    assert "r1" not in result["parameters_below_target"]  # halted → loop can finalize


def test_stall_does_not_fire_without_audit():
    session_store.add("stall-test", {"progress_log": []})
    rec = _flat_record(audit_iteration=None, history_len=3)  # never audited
    result = asyncio.run(benchmarking(_bench_state(rec)))
    r = result["parameter_records"]["r1"]
    assert r["status"] == "optimizing"
    assert "r1" in result["parameters_below_target"]


def test_stall_does_not_fire_when_improving():
    session_store.add("stall-test", {"progress_log": []})
    rec = _flat_record(audit_iteration=1, history_len=3)
    # prior history all 0.2; this pass computes 0.5 (preds give TP=1/FP=1 over target-0.9 gt) →
    # a real improvement in the latest iteration → iters_without_improvement resets to 0.
    for h in rec["iteration_history"]:
        h["accuracy"] = 0.2
    rec["best_accuracy"] = 0.2
    rec["initial_accuracy"] = 0.2
    result = asyncio.run(benchmarking(_bench_state(rec)))
    r = result["parameter_records"]["r1"]
    assert r["status"] == "optimizing"
    assert r["iterations_without_improvement"] == 0


# ─────────────────────────── Change 2: label_limited halt ───────────────────────────

def _audit_state(session_id):
    conv = {"conversation_id": "c1", "transcript": [{"speaker": "agent", "msg": "hi"}]}
    rec = _flat_record(audit_iteration=None, history_len=3)
    return {
        "session_id": session_id, "current_iteration": 5,
        "parameters_below_target": ["r1"], "parameters_meeting_target": [],
        "parameter_records": {"r1": rec},
        "ground_truth_map": {"c1": {"r1": "Yes"}},
        "conversations": [conv], "llm_config": {"model": "x"},
    }


def test_label_limited_halt_on_inconsistency(monkeypatch):
    import agents.nodes.gt_alignment_audit as mod

    async def fake_audit(*a, **k):
        return "Gap type: LABELLING_INCONSISTENCY\nAlignment gaps: None.\nRevised optimization strategy: relabel."

    monkeypatch.setattr(mod, "_run_audit", fake_audit)
    monkeypatch.setattr(mod, "get_llm", lambda **k: type("L", (), {"model_name": "x"})())
    session_store.add("halt-test", {"progress_log": []})

    result = asyncio.run(mod.gt_alignment_audit(_audit_state("halt-test")))
    r = result["parameter_records"]["r1"]
    assert r["status"] == "label_limited"
    assert r["stop_reason"] == "label_inconsistency"
    assert result["parameters_below_target"] == []  # halted


def test_label_limited_respects_disable_flag(monkeypatch):
    import agents.nodes.gt_alignment_audit as mod
    from config import settings

    async def fake_audit(*a, **k):
        return "Gap type: LABELLING_INCONSISTENCY\nAlignment gaps: None."

    monkeypatch.setattr(mod, "_run_audit", fake_audit)
    monkeypatch.setattr(mod, "get_llm", lambda **k: type("L", (), {"model_name": "x"})())
    monkeypatch.setattr(settings, "enable_label_limited_halt", False)
    session_store.add("halt-test2", {"progress_log": []})

    result = asyncio.run(mod.gt_alignment_audit(_audit_state("halt-test2")))
    r = result["parameter_records"]["r1"]
    assert r["status"] != "label_limited"          # not halted when disabled
    assert "parameters_below_target" not in result  # below_target untouched


def test_description_mismatch_does_not_halt(monkeypatch):
    import agents.nodes.gt_alignment_audit as mod

    async def fake_audit(*a, **k):
        return "Gap type: DESCRIPTION_MISMATCH\nAlignment gaps: wrong scope."

    monkeypatch.setattr(mod, "_run_audit", fake_audit)
    monkeypatch.setattr(mod, "get_llm", lambda **k: type("L", (), {"model_name": "x"})())
    session_store.add("mismatch-test", {"progress_log": []})

    result = asyncio.run(mod.gt_alignment_audit(_audit_state("mismatch-test")))
    r = result["parameter_records"]["r1"]
    assert r["status"] != "label_limited"
    assert "parameters_below_target" not in result
