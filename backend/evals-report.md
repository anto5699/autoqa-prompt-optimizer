# Agentic Evals Report

**Run:** 2026-06-30 14:23  
**Duration:** 109.4s

---

## Summary

| Result | Count |
|--------|-------|
| ✅ Passed | 9 |
| ❌ Failed | 8 |
| 💥 Errors | 0 |
| **Total** | **17** |

**Overall pass rate:** 9/17 (53%)

---

## Results by Node

| Node | Passed | Total | Status |
|------|--------|-------|--------|
| RCA Analyzer | 4 | 5 | ⚠️ 4/5 |
| Prompt Optimizer | 3 | 5 | ⚠️ 3/5 |
| GT Alignment Audit | 1 | 4 | ⚠️ 1/4 |
| Mid-Loop Clarification | 1 | 3 | ⚠️ 1/3 |

---

## Failed Scenarios

| Scenario | Node | Score detail |
|----------|------|-------------|
| `align-inconsistent-001` | GT Alignment Audit | strategy_clarity=0.70 | non_hallucination=1.00 |
| `align-nogap-001` | GT Alignment Audit | strategy_clarity=0.00 | non_hallucination=0.70 |
| `align-scope-001` | GT Alignment Audit | strategy_clarity=1.00 | non_hallucination=0.40 |
| `clarify-ambiguous-001` | Mid-Loop Clarification | scenario = {'conversations': [{'ground_truth': 'No', 'id': 'c1', 'prediction': 'Yes', 'transcript': [{'msg': 'My account |
| `clarify-fallback-001` | Mid-Loop Clarification | scenario = {'conversations': [{'ground_truth': 'Yes', 'id': 'c1', 'prediction': 'Yes', 'transcript': [{'msg': "I'll tran |
| `opt-nochange-001` | Prompt Optimizer | functional_correctness=0.00 | generalisation=1.00 | format_compliance=1.00 |
| `opt-stagnant-001` | Prompt Optimizer | functional_correctness=1.00 | generalisation=0.40 | format_compliance=1.00 |
| `rca-fn-002` | RCA Analyzer | actionability=0.40 | non_hallucination=0.70 |

---

## Dimension Score Averages

A consistently low dimension (< 0.65) is the actionable signal — it identifies which aspect of the node to improve next.

| Dimension | Avg Score | Signal |
|-----------|-----------|--------|
| `actionability` | 0.40 | 🔴 Investigate |
| `functional_correctness` | 0.50 | 🔴 Investigate |
| `strategy_clarity` | 0.57 | 🔴 Investigate |
| `non_hallucination` | 0.70 | 🟡 Watch |
| `generalisation` | 0.70 | 🟡 Watch |
| `format_compliance` | 1.00 | 🟢 Healthy |

---

## Recommended Next Steps

8 scenario(s) failed. Prioritise fixes in this order:

1. **RCA Analyzer** — Failures here cascade: a bad RCA feeds bad optimizer input.
   - Check `agents/nodes/rca_analyzer.py` system prompt specificity
2. **Prompt Optimizer** — Description rewrites not addressing the RCA.
   - Review optimizer system prompt: does it explicitly instruct addressing the RCA?
3. **GT Alignment Audit** — Misses real gaps or hallucinates non-existent ones.
   - Review `agents/nodes/gt_alignment_audit.py` system prompt for gap detection clarity
4. **Mid-Loop Clarification** — Questions not targeted or not in plain language.
   - Review `agents/nodes/mid_loop_clarification.py` audience instructions

**Low-scoring dimensions** (< 0.65): `strategy_clarity`, `functional_correctness`, `actionability`
These are cross-scenario signals — fixing the node prompt for this dimension improves multiple scenarios.
