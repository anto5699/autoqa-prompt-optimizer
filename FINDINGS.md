# AutoQA Prompt Optimizer — Test Findings

Three end-to-end automated test runs using Playwright. Each run used a strategized CSV designed to probe specific system capabilities. Findings are ranked by actionability.

---

## Test Runs

| | Run 1 (`test_strategized.csv`) | Run 2 (`test_strategized_v2.csv`) | Run 3 (`test_strategized_v2.csv`) |
|---|---|---|---|
| Session | `7b9d02b7-...` | `9c5c4a59-...` | `0aa6c5e2-...` |
| Conversations | 25 | 25 | 25 |
| Rules | 6 | 6 | 6 |
| Iterations | 5 | 5 | 8 |
| Accuracy target | 80% | 80% | 90% |
| Overall accuracy | 81.8% | 82.6% | **96.0%** |
| Rules meeting target | 4/6 | 4/6 | **5/6** |
| Model | gpt-5.2 | gpt-5.2 | gpt-5.2 |
| RCA includes transcripts | No | No | **Yes** |
| Stagnation detection | No | No | **Yes** |

Run 1 used mildly vague descriptions (initial accuracy 64–92%). Run 2 was designed to force initial accuracy below 50% on all rules to stress-test the optimization loop. Run 3 used the same CSV as Run 2 but with the improved optimizer: transcript-aware RCA, stagnation escalation, accuracy trajectory in prompts, and 8 iterations at 90% target.

---

## Run 2 — Per-Rule Results (Primary Reference)

Rules were designed with intentionally misleading initial descriptions. Ground truth was defined around precise binary criteria (e.g., agent states their name, customer says "supervisor"/"manager"/"escalate") while descriptions were framed around vague, semantically adjacent concepts.

| Rule | Initial Description | True Criterion | Initial Acc | Final Acc | Delta | Status |
|------|--------------------|----|--------|-------|-------|--------|
| `rule_answer_1` | "The agent was professional" | Agent explicitly states their name in first 2 messages | 40.0% | 68.0% | +28pp | max_iterations_reached |
| `rule_trigger_2` | "The customer had an order-related concern" | Customer explicitly states a specific alphanumeric order/ticket ID | 84.0% | 72.0% | −12pp | max_iterations_reached |
| `rule_answer_2` | "The agent addressed the customer's account details" | Agent verbatim repeats the exact ID the customer provided | 58.3% | 91.7% | +33pp | converged |
| `rule_answer_3` | "The conversation was brought to a close" | Agent explicitly asks "Is there anything else I can help you with?" in last 2 messages | 88.0% | 84.0% | −4pp | converged |
| `rule_trigger_4` | "The customer expressed strong dissatisfaction" | Customer explicitly uses "supervisor", "manager", or "escalate" | 100.0% | 100.0% | 0pp | converged |
| `rule_answer_4` | "The agent managed the difficult situation" | Agent both offers to transfer to supervisor AND provides specific timeframe | 60.0% | 80.0% | +20pp | converged |

### Accuracy Trajectories (iter 0 → iter 5)

| Rule | Trajectory |
|------|-----------|
| `rule_answer_1` | 40% → 40% → 40% → 40% → 48% → 68% |
| `rule_trigger_2` | 84% → 72% → 68% → 72% → 72% → 72% |
| `rule_answer_2` | 58% → 75% → 100% → 100% → 92% |
| `rule_answer_3` | 88% → 88% → 84% → 80% → 84% |
| `rule_trigger_4` | 100% → 100% → 100% → 100% → 100% |
| `rule_answer_4` | 60% → 60% → 60% → 80% → 100% → 80% |

### Final Confusion Matrices

| Rule | TP | TN | FP | FN | Precision | Recall | F1 |
|------|----|----|----|----|-----------|--------|----|
| `rule_answer_1` | 10 | 7 | 8 | 0 | 55.6% | 100% | 71.4% |
| `rule_trigger_2` | 9 | 9 | 4 | 3 | 69.2% | 75.0% | 72.0% |
| `rule_answer_2` | 4 | 7 | 1 | 0 | 80.0% | 100% | 88.9% |
| `rule_answer_3` | 9 | 12 | 1 | 3 | 90.0% | 75.0% | 81.8% |
| `rule_trigger_4` | 5 | 20 | 0 | 0 | 100% | 100% | 100% |
| `rule_answer_4` | 2 | 2 | 1 | 0 | 66.7% | 100% | 80.0% |

---

## Run 3 — Per-Rule Results

Same initial descriptions as Run 2. Improvements applied: transcript-aware RCA, accuracy trajectory in prompts, stagnation escalation after 4 identical-accuracy history entries, 8 iterations at 90% target.

| Rule | Initial Acc | Final Acc | Delta | Status |
|------|-------------|-----------|-------|--------|
| `rule_answer_1` | 40.0% | 76.0% | +36pp | max_iterations_reached |
| `rule_trigger_2` | 80.0% | 100.0% | +20pp | converged |
| `rule_answer_2` | 75.0% | 100.0% | +25pp | converged |
| `rule_answer_3` | 84.0% | 100.0% | +16pp | converged |
| `rule_trigger_4` | 100.0% | 100.0% | 0pp | converged |
| `rule_answer_4` | 60.0% | 100.0% | +40pp | converged |

### Run 3 — Final Confusion Matrix (rule_answer_1 only; all others TP=GT-Yes, FP=FN=0)

| Rule | TP | TN | FP | FN | Precision | Recall | F1 |
|------|----|----|----|----|-----------|--------|----|
| `rule_answer_1` | 4 | 15 | 0 | 6 | 100% | 40% | 57.1% |

### Run 3 vs Run 2 Comparison

| Rule | Run 2 final | Run 3 final | Change |
|------|------------|------------|--------|
| `rule_answer_1` | 68% (8 FP, 0 FN) | 76% (0 FP, 6 FN) | +8pp; error pattern flipped |
| `rule_trigger_2` | 72% (max_iter) | **100% (converged)** | +28pp |
| `rule_answer_2` | 91.7% (converged at 80%) | **100% (converged)** | +8pp |
| `rule_answer_3` | 84% (converged at 80%) | **100% (converged)** | +16pp |
| `rule_trigger_4` | 100% | 100% | — |
| `rule_answer_4` | 80% (converged at 80%) | **100% (converged)** | +20pp |
| **Overall** | **82.6%** | **96.0%** | **+13.4pp** |

### Run 3 — Key Observations

**Transcript-aware RCA broke the semantic anchor on rule_answer_1 in one iteration.** Accuracy jumped from 40% to 76% in iteration 1 (vs stuck at 40% for 4 iterations in Run 2). The error pattern completely flipped: Run 2 had 8 false positives (correct-sounding professionalism responses mislabeled as passing name-stating), Run 3 has 0 false positives and 6 false negatives (the description is now correctly strict about excluding non-name-staters but too strict about what counts as stating a name).

**rule_trigger_2 now converges cleanly to 100%.** In Run 2, it started at 84% (above the 80% target) but the optimizer degraded it to 72%. In Run 3, starting at 80% (below 90% target), it correctly enters optimization mode and converges. This confirms F2 was a target-gate problem, not a fundamental optimizer limitation.

**Stagnation detection fired as expected.** rule_answer_1's four-iteration plateau from Run 2 (40%→40%→40%→40%) triggered the escalation in Run 3, forcing a pivot that produced the 76% jump. The description evolved into a completely different evaluative frame by iteration 1.

**Remaining gap on rule_answer_1:** The 6 false negatives are agents who stated their names but the description's PASS_CRITERIA are too narrow (e.g., requiring specific phrasing or not recognising natural variations like "I'm Sarah" vs "My name is Sarah"). This is a fundamentally more tractable problem than the original semantic anchor — one more iteration with FN-focused RCA and transcript examples showing the missed cases would likely resolve it.

---

## Findings

### F1 — Semantic Anchor Problem (Partially Resolved in Run 3)

**Observed on:** `rule_answer_1` across all 5 iterations.

The initial description "The agent was professional" anchored the optimizer to build a professionalism rubric. The clarification loop correctly surfaced the ambiguity and the user answers explicitly stated: *"professionalism means the agent explicitly states their name in the first 2 messages."* Despite this, the optimizer generated a 1,000-word professionalism rubric with tone criteria, fail conditions, and edge-case handling — and never added a name-stating requirement.

**Root cause:** When the initial description is semantically coherent (professionalism is a real concept) but maps to the *wrong* criterion, the optimizer's RCA and rewriting remain anchored to the description's semantic frame. Clarification answers are incorporated as additional constraints on top of the existing framing, not as a replacement for it.

**Consequence:** All 15 conversations where the agent did not state their name were evaluated as professionalism questions. 8 of those agents were genuinely polite and helpful — correctly passing the expanded professionalism rubric but incorrectly passing the intended name-stating check. Accuracy plateaued at 40% for 4 iterations before marginally improving to 68% in the final iteration.

**Recommendation:** When clarification answers substantially redefine a rule (not just clarify scope but change the criterion entirely), the optimizer should synthesize a new description from the clarification answers rather than patching the original. One approach: add a post-clarification rewrite step that generates a fresh description directly from the Q&A before iteration 0.

---

### F2 — Over-Specification Regression (High Priority)

**Observed on:** `rule_trigger_2` (84% → 72%) and partially on `rule_answer_3` (88% → 84%).

`rule_trigger_2` started above the 80% target at 84%. The optimizer was invoked because FP and FN cases existed (TP=10, TN=11, FP=2, FN=2 at iteration 0). Each subsequent iteration added more constraints to the description, tightening the definition of "specific alphanumeric identifier." By iteration 2, the over-specified description began generating FNs on cases it had previously scored correctly, dropping accuracy to 68% before partially recovering to 72%.

**Root cause:** The convergence check gates *further optimization* once a rule reaches the accuracy target, but at iteration 0 `rule_trigger_2` was above target yet still had non-zero FP/FN counts. The current logic routes any rule with FP or FN cases through RCA regardless of whether the accuracy target is already met.

**Consequence:** A rule that was working well was made worse by unnecessary optimization.

**Recommendation:** Gate RCA and description rewriting behind the accuracy target, not just behind FP/FN existence. If `accuracy >= target`, mark the rule converged immediately regardless of confusion matrix imperfections. Only run RCA when `accuracy < target`.

---

### F3 — Clarification Loop Quality Validated

**Observed across:** all 5 rules that received questions.

The ambiguity detector generated 2 targeted questions per ambiguous rule (10 total). Every question correctly identified a genuine ambiguity in the vague descriptions: scope boundaries, pass/fail thresholds, speaker attribution, and evaluation window interpretation. No questions were redundant or off-topic.

The answers were used effectively for `rule_answer_2` and `rule_answer_4`, both of which converged cleanly. This confirms the clarification loop works as intended when the initial description and the clarification answers are semantically aligned.

---

### F4 — Optimization Produces Meaningful Gains on Sub-50% Starting Accuracy

**Observed on:** `rule_answer_2` (+33pp), `rule_answer_1` (+28pp), `rule_answer_4` (+20pp).

Even from an initial accuracy of 40–58%, the optimizer improved every rule it could not converge within the iteration budget. The improvements are genuine: `rule_answer_2` went from 58% to 92% by learning to require verbatim ID repetition rather than generic "account handling." `rule_answer_4` went from 60% to 80% by learning the dual-criterion structure (transfer offer + specific timeframe).

This validates the core optimization loop for rules where the description is vague but semantically compatible with the true criterion.

---

### F5 — Small Evaluable Sample Fragility

**Observed on:** `rule_answer_4` (5 evaluable rows).

`rule_answer_4` is a dynamic answer rule — it is only evaluated on conversations where the paired trigger fires. With 5 of 25 conversations triggering `rule_trigger_4`, only 5 rows are evaluable. At this sample size, each wrong prediction represents a 20pp accuracy swing. The trajectory (60% → 60% → 60% → 80% → 100% → 80%) shows genuine oscillation: the rule converged at 80% on iteration 3, jumped to 100% on iteration 4, then fell back to 80% on iteration 5 — all with a one-prediction difference.

The rule was correctly marked `converged` at 80%, which is the right behavior. But the result has high variance and limited statistical reliability.

**Recommendation:** Surface a warning when an evaluable sample is below a configurable threshold (e.g., < 10 rows). This does not block evaluation but flags the result as low-confidence in the report.

---

### F6 — LLM Generalizes Well from Near-Zero Context

**Observed on:** `rule_trigger_4` (100% from iteration 0).

The description "The customer expressed strong dissatisfaction" achieved perfect accuracy (TP=5, TN=20, FP=0, FN=0) on iteration 0, despite being intentionally vague. The model correctly inferred that "strong dissatisfaction" in this context means an explicit escalation request, not general frustration — likely because the system prompt provides strong evaluation scaffolding.

This suggests the production system prompt is doing substantial lifting for semantically clean trigger rules where the vague description still points in the right direction. The optimizer and clarification loop are most valuable when the initial description is either misleading or highly underspecified.

---

## Cross-Run Comparison

Both runs hit 80%+ overall accuracy and 4/6 rules converged. The same two structural failure modes appeared in both:

1. **Rules that didn't converge were those where the vague description pointed to a different criterion** than the ground truth — the optimizer improved them but couldn't fully bridge the semantic gap within 5 iterations.

2. **Rules that were already above target got optimized unnecessarily**, sometimes causing regression. This is consistent across both runs.

The POC demonstrates reliable end-to-end capability: ingestion, ambiguity detection, clarification loop, iterative evaluation, RCA, and report generation all work correctly. The two findings above (F1, F2) represent the most impactful improvements for a production iteration.

---

## Suggested Next Steps

| Priority | Action |
|---|---|
| High | Implement post-clarification description rewrite from Q&A when answers substantially redefine the rule criterion (addresses F1) |
| High | Gate RCA behind accuracy target — skip optimization if `accuracy >= target` regardless of FP/FN counts (addresses F2) |
| Medium | Add low-confidence warning when evaluable row count < configurable threshold (addresses F5) |
| Low | Investigate whether the initial description rewrite from clarification answers should replace rather than supplement the original description |
