# Task: Capture evaluator justifications and feed them into RCA

**For:** Claude Code
**Project:** AutoQA Prompt Optimization System
**Read first:** `CLAUDE.md` (rules + terminology), `SPEC.md` (schema/nodes), `MILESTONES.md` (build order).
**Type:** Enhancement to the agentic optimization loop. Backend only (no frontend changes required for v1).

---

## 1. Background — what exists today

The optimization loop runs `evaluator → benchmarking → rca_analyzer → prompt_optimizer`.

- The **evaluator** (`backend/agents/nodes/evaluator.py`) sends each Conversation + a batch of Parameters to the LLM and parses a JSON array of `{"_id", "isQualified", ...}` objects. It records only the verdict as `"Yes"`/`"No"` into `record["current_predictions"][conv_id]` (lines ~110–115). It ignores everything else in each object.
- The **RCA agent** (`backend/agents/nodes/rca_analyzer.py`) reconstructs failures from `current_predictions` vs `ground_truth_map`, then re-sends the raw transcript to the LLM and asks it to *hypothesise* why the wording failed. It never sees how the evaluator actually interpreted the Parameter.

### Critical fact — read before scoping

The evaluator's system prompt (`DEFAULT_SYSTEM_PROMPT` in `backend/config.py`, lines ~41–45) **already instructs the model to return a per-rule `rationale`**:

```
{"_id": "<rule_id>", "isQualified": true, "rationale": "<one sentence>"}
```

The model is already generating this field and paying the token cost for it. The evaluator code simply discards it. So this task is mostly *stop discarding the justification and route it into RCA* — not *add a new LLM output*.

---

## 2. Goal

Capture the evaluator's per-Parameter justification for every Conversation it evaluates, persist it in state for the current Iteration, and surface the justifications for error cases to the RCA agent so its root cause analysis is grounded in how the evaluator actually read the Evaluation prompt — rather than re-hypothesising from the transcript alone.

Definition of done: RCA prompts include, for each error case, the evaluator's stated reason for its verdict, and accuracy math / existing tests are unaffected.

---

## 3. Hard constraints (from CLAUDE.md — do not violate)

1. **No transcript logging (rule 2).** Justifications will quote transcript content. They may live in `parameter_records` state, but must **never** be passed to `session_store.append_log`, `progress_log`, `append_trace`, or any logger/console output. Audit every new line for this.
2. **No fabricated metrics (rule 6).** Justifications feed RCA only. They must not influence the confusion matrix, accuracy, or any metric. Do not change benchmarking math.
3. **NA exclusion (rule 3) + RCA scope (rule 8).** Do not collect or analyse justifications for NA ground truths or for Parameters already at/above the Accuracy target. Reuse the existing gates in `_collect_error_cases`.
4. **Canonical parameter names (rule 9).** Do not transform any `parameter_name` / `rule_id`.
5. **Domain terminology.** Use Parameter / Evaluation prompt / Ground truth / Adhered–Not Adhered–Not Applicable / Iteration in any user-facing strings, comments, and log messages. The internal field may be called `current_rationales` for parity with `current_predictions`.
6. **Model is fixed (rule 1).** Do not change the model or the evaluator's verdict contract. The `rationale` field is already in the prompt.

---

## 4. Plan (do this first, then implement)

Produce a short written plan before editing, covering: the four file changes below, the state-reset points, the JSON-robustness change, and the test list. Confirm the plan against the constraints above, then implement.

---

## 5. Implementation

### 5.1 `backend/agents/state.py` — add a parallel field
Add to `RuleRecord`, directly beneath `current_predictions: Dict[str, str]`:

```python
current_rationales: Dict[str, str]  # conv_id -> evaluator's stated reason for this iteration's verdict
```

Notes:
- Store **current Iteration only** — no history. Keeps memory bounded; RCA only reads current-iteration errors.
- Anywhere a new `RuleRecord` is constructed/initialised, initialise `current_rationales: {}` so the key always exists. Search the codebase for where records are first built (baseline/ingestion path) and where `current_predictions: {}` is set, and mirror it.

### 5.2 `backend/agents/nodes/evaluator.py` — capture, reset, and default
- **Reset alongside predictions.** Where predictions are reset for non-converged rules (line ~48, `{**records[rule_id], "current_predictions": {}}`), also reset `"current_rationales": {}`.
- **Capture on success.** In the results loop (lines ~110–115), after computing `is_qualified`, also store:
  ```python
  records[rule_id]["current_rationales"][conv_id] = (rule_result.get("rationale") or "")[:500]
  ```
  Truncate defensively (e.g. 500 chars) to bound state size and prompt bloat.
- **Default on every failure path.** Anywhere the code defaults a verdict to `"No"` because of timeout, retries exhausted, JSON parse failure, or whole-conversation exception (lines ~106–108, ~225, ~238), also set the rationale to `""`. The rationale map must have the same keys as the predictions map for every evaluated rule.
- **Harden JSON parsing (important — see Risks).** Free-form rationale text raises malformed-JSON risk, and the current parser defaults the *entire batch* to `"No"` on any failure. Before depending on `rationale`, make parsing more tolerant: on a batch-level `json.loads` failure, attempt per-object recovery (e.g. extract individual `{...}` objects) instead of discarding all six rules' verdicts. If you cannot recover an object, keep the existing default-to-`"No"` + `rationale=""` behaviour for that rule only. Do not log transcript or rationale content in these warnings.

### 5.3 `backend/agents/nodes/rca_analyzer.py` — carry and inject the justification
- In `_collect_error_cases` (lines ~66–89), the function currently takes `predictions`. Pass `record["current_rationales"]` in as well (update the call site at line ~51–53), and add to each error dict:
  ```python
  "rationale": rationales.get(conv_id, ""),
  ```
- In `_run_rca`, in the `cases_text` join (lines ~127–132), add a line per case:
  ```
  Evaluator's stated reason: {e['rationale'] or '(none provided)'}
  ```
- **Frame it as evidence, not truth.** In the `ask`/instruction text, add a sentence such as: *"The evaluator's stated reason shows how the wording was interpreted. Treat it as evidence of the interpretation, not as a confirmed cause — cross-check it against the transcript."* This guards against post-hoc rationalisation (see Risks).
- Keep the existing plain-English output format and the banned-terms list intact.

### 5.4 (Recommended, optional) Improve justification faithfulness
In `DEFAULT_SYSTEM_PROMPT` (`backend/config.py`), tighten the `rationale` instruction so it must **quote the specific transcript utterance** that drove the verdict, e.g.:
`"rationale": "<one sentence citing the exact transcript words that determined the verdict>"`.
A span-citing rationale is verifiable and far more useful to RCA than a free-form sentence. Do not change `isQualified` semantics or the JSON shape otherwise. If you make this change, re-run evaluator tests since the prompt text is asserted in some fixtures.

---

## 6. Tests

Add/extend tests under `backend/tests/` (match existing style, e.g. `test_evaluator_skip.py`):

1. **Evaluator captures rationale.** Mock an LLM batch response containing `rationale`; assert `current_rationales[conv_id]` is populated and truncated, and that `current_predictions` is unchanged.
2. **Failure paths default rationale.** Simulate JSON parse failure / timeout; assert every evaluated rule has a `""` rationale and the verdict defaults to `"No"`, with prediction and rationale maps sharing identical keys.
3. **Partial JSON recovery.** Feed a batch where one object is malformed and the rest are valid; assert only the malformed rule defaults, the others keep their verdicts + rationales.
4. **RCA injection.** Assert the RCA prompt string contains the evaluator's stated reason for an error case, and that NA / at-target Parameters contribute no cases (rules 3 and 8).
5. **No leakage.** Assert no log/trace/progress_log call receives rationale or transcript content (grep the new code paths; add an explicit assertion where practical).

Run the suite: `cd backend && source venv/bin/activate && pytest -q`. All existing tests must still pass.

---

## 7. Risks to keep in mind

- **Post-hoc rationalisation.** The rationale may not faithfully reflect the computation that produced `isQualified`. Mitigated by framing it as evidence in RCA (5.3) and by span-citation (5.4). Never let RCA treat it as the definitive cause.
- **JSON fragility (highest practical risk).** Adding free-form text to batched output raises malformed-JSON odds, and the current whole-batch default-to-No is a silent prediction corruptor. The hardening in 5.2 is the most important part of this task — do it even though it's "just plumbing."
- **State growth.** Bounded by current-iteration-only storage + truncation. Do not add rationale history.
- **Logging compliance.** Re-audit before finishing: no rationale or transcript text in any log/trace.

---

## 8. Out of scope for v1
No frontend display of justifications, no persistence of rationale across Iterations, no change to metrics, the report schema, or the LLM/model. Note these as possible follow-ups; do not build them.

## 9. Acceptance checklist
- [ ] `current_rationales` added to `RuleRecord` and initialised everywhere `current_predictions` is.
- [ ] Evaluator captures, truncates, resets per Iteration, and defaults rationale on all failure paths.
- [ ] Batch JSON parsing recovers per-object instead of defaulting whole batches.
- [ ] RCA error cases carry and display the evaluator's stated reason, framed as evidence.
- [ ] No rationale/transcript content reaches any log, trace, or progress_log.
- [ ] Metrics and accuracy math unchanged; all existing + new tests pass.
