# Agentic Evals Report

**Run:** 2026-07-01 13:27  
**Duration:** 141.1s

---

## Summary

| Result | Count |
|--------|-------|
| ✅ Passed | 25 |
| ❌ Failed | 0 |
| 💥 Errors | 0 |
| **Total** | **25** |

**Overall pass rate:** 25/25 (100%)

---

## Results by Node

| Node | Passed | Total | Status |
|------|--------|-------|--------|
| RCA Analyzer | 5 | 5 | ✅ All pass |
| Prompt Optimizer | 5 | 5 | ✅ All pass |
| GT Alignment Audit | 4 | 4 | ✅ All pass |
| Mid-Loop Clarification | 3 | 3 | ✅ All pass |
| End-to-End | 4 | 4 | ✅ All pass |

---

## Recommended Next Steps

All scenarios passed. The optimization pipeline is handling all documented failure modes correctly.

**Suggested actions:**
- Add adversarial or edge-case scenarios to push quality higher
- Run E2E evals against real CSV data to validate end-to-end convergence
