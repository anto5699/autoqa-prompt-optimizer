# MILESTONES.md — AutoQA Prompt Optimization System
# Build order, completion criteria, definition of done
# Rules in CLAUDE.md. Schemas in SPEC.md.

---

## OPEN ITEMS

**OI-1 — V2 system prompt NA support:** The V2 evaluation system prompt as supplied emits only `isQualified: true/false`; CONDITION-not-triggered and EXCEPTION cases therefore cannot yield NA until the V2 system prompt is extended to emit `isQualified: null` (or a `verdict` field). Verdict mapping is already forward-compatible (`_verdict_from_v2_result`).

**OI-2 — Scope units mismatch (turns vs messages):** The V2 authoring spec (Appendix A §2, §6) defines Scope as `entire | first_n_turns | last_n_turns` where a Turn = one customer block + one agent block. The V2 evaluation system prompt scopes by messages via `evaluation_type ∈ {entire, first, last}` + `n_messages`. These are different units. The UI currently exposes message-count directly (to match the system prompt that runs). This must be resolved with the V2 engine owners — turns-to-messages conversion logic is not yet implemented.

---

## Build Order

Complete and verify each phase before starting the next. Never skip the ✅ checks.

---

## Phase 1 — Foundation
**Goal:** Core utilities and state definitions. No LLM calls.

- [ ] Full directory structure per SPEC.md (all `__init__.py` files included)
- [ ] `requirements.txt` — include: `fastapi`, `uvicorn`, `langgraph>=0.2`, `langchain-anthropic`, `pydantic>=2.7`, `pydantic-settings`, `pandas>=2.2`, `sse-starlette`, `pytest`
- [ ] `config.py` — pydantic-settings, expose `settings` singleton
- [ ] `utils/csv_parser.py` — all validation rules from SPEC.md CSV section
- [ ] `agents/state.py` — full TypedDict definitions with `Annotated` reducer on `progress_log`
- [ ] `utils/session_store.py` — thread-safe dict: `add`, `get`, `update`, `delete`
- [ ] `utils/accuracy_metrics.py` — `compute_metrics()` returning TP/TN/FP/FN + 4 metrics, NA exclusion
- [ ] `main.py` — FastAPI app factory with CORS (routes can 404 at this stage)
- [ ] `tests/test_csv_parser.py` and `tests/test_accuracy_metrics.py`

### ✅ Phase 1 Complete When
- `pytest tests/` passes for csv_parser and accuracy_metrics (valid + invalid inputs, NA exclusion edge cases)
- `uvicorn main:app` starts without errors

---

## Phase 2 — Core Optimization Loop (Happy Path)
**Goal:** End-to-end graph execution, one pass only (no clarification, no RCA loop).

- [ ] `nodes/csv_ingestion.py`
- [ ] `nodes/baseline_prompt_generator.py`
- [ ] `nodes/evaluator.py` — async batching with semaphore per SPEC.md
- [ ] `nodes/benchmarking.py`
- [ ] `nodes/finalize.py`
- [ ] `agents/graph.py` — happy path only: csv_ingestion → baseline → evaluator → benchmarking → convergence_check → finalize; no interrupt, no RCA loop
- [ ] `api/routes/sessions.py` — `POST /api/sessions` and `GET /api/sessions/:id`
- [ ] `api/schemas/session.py` and `api/schemas/report.py`

### ✅ Phase 2 Complete When
- `POST /api/sessions` with a 10-row CSV returns `session_id`
- `GET /api/sessions/:id` shows `current_phase` advancing to `"complete"`
- Final `OptimizationState.final_report` is non-null and all parameter `status` values are `"converged"` or `"max_iterations_reached"` (not `"pending"`)
- Verified by inspecting graph state directly (not via report endpoint — that's Phase 5)

---

## Phase 3 — Clarification Loop
**Goal:** Ambiguity detection, clarifying questions, interrupt + resume.

- [ ] `nodes/ambiguity_detection.py` — LLM call, question generation, `interrupt()` call
- [ ] Update `agents/graph.py` — add ambiguity_detection node between csv_ingestion and baseline_prompt_generator; handle interrupt routing
- [ ] `api/routes/sessions.py` — add `POST /api/sessions/:id/answers` using `Command(resume=...)`

### ✅ Phase 3 Complete When
- CSV with a vague parameter (e.g. "Agent handled the call appropriately") triggers `current_phase = "awaiting_clarification"` with non-empty `clarifying_questions`
- `POST /answers` returns `"status": "resumed"` and graph continues to completion
- CSV with unambiguous parameters skips clarification entirely

---

## Phase 4 — RCA + Iterative Optimization
**Goal:** Root cause analysis on below-target parameters, iterative prompt refinement.

- [ ] `nodes/rca_analyzer.py`
- [ ] `nodes/prompt_optimizer.py`
- [ ] Update `agents/graph.py` — wire loop: benchmarking → convergence_check → rca_analyzer → prompt_optimizer → evaluator
- [ ] Verify `iteration_history` has one entry per completed iteration per parameter
- [ ] Verify `current_predictions` is reset to `{}` at the start of each new evaluator pass

### ✅ Phase 4 Complete When
- With a CSV where no parameter starts ≥80%: at least one parameter's accuracy improves across iterations
- Parameters at `max_iterations` have `status = "max_iterations_reached"` with non-null `rca_findings`
- `iteration_history` length = number of completed iterations for each parameter

---

## Phase 5 — Streaming + Full API
**Goal:** SSE progress stream, report endpoint, session cleanup.

- [ ] `api/routes/stream.py` — `GET /api/sessions/:id/stream` (SSE) with correct headers
- [ ] `GET /api/sessions/:id/report` — 200 with report or 202 if in progress
- [ ] `DELETE /api/sessions/:id`
- [ ] SSE fires `progress` at every phase transition, `complete` on finish, `error` on failure

### ✅ Phase 5 Complete When
- `curl -N http://localhost:8000/api/sessions/:id/stream` shows events at each phase
- `GET /report` returns full report JSON matching SPEC.md Report Schema
- `DELETE` returns 204 and session is gone from store

---

## Phase 6 — Angular Frontend
**Goal:** 4-step UI wired to all API endpoints. Spec in SPEC.md Angular section.

- [ ] `session.service.ts` — `createSession()`, `getSession()`, `submitAnswers()`
- [ ] `sse.service.ts` — wraps EventSource, exposes `progress$` and `complete$` observables
- [ ] Upload component (Step 1)
- [ ] Clarification component (Step 2)
- [ ] Progress component (Step 3) — SSE + 3s poll
- [ ] Results component (Step 4) — parameter table, per-rule detail panel (before/after, confusion matrix, trend chart, optimization notes, prompt comparison), 3 export buttons
- [ ] Print report component — hidden screen component for PDF export via `window.print()`; contains overall KPIs, per-parameter table, per-rule confusion matrix, trend chart, optimization notes, original vs final prompt
- [ ] `styles.css` — global reset, typography, CSS variables for green/amber/red status colours (green ≥90%, amber 80–89%, red <80%)
- [ ] Component-level CSS for each page

### ✅ Phase 6 Complete When
- Full end-to-end flow in browser using the real CSV with no console errors
- SSE progress visible live on the Progress page
- Results page shows final prompt (copy button works), confusion matrix, iteration trend, optimization notes
- Export Evaluations CSV downloads wide-format CSV (one row per conversation)
- Export Prompts CSV downloads parameter_name, rule_type, optimised_prompt
- Export Report PDF opens print dialog with full formatted report

---

## Definition of Done (Prototype)

- [ ] CSV with ≥25 rows and ≥3 parameters completes end-to-end without errors
- [ ] At least one parameter triggers clarifying questions
- [ ] At least one parameter's accuracy improves across iterations
- [ ] Converged parameters: `status = "converged"`, `rca_findings = null`
- [ ] Below-target parameters: `status = "max_iterations_reached"`, `rca_findings` non-null
- [ ] Regression warning appears in report when a rule's best accuracy exceeded target but final did not
- [ ] Evaluations CSV export is wide-format (one row per conversation, column group per rule)
- [ ] Prompts CSV export contains parameter_name, rule_type, optimised_prompt for all rules
- [ ] PDF report renders with overall KPIs, per-parameter table, confusion matrix, trend chart, and prompt text
- [ ] SSE events fire at every phase transition
- [ ] All 5 API endpoints return correct status codes and shapes
- [ ] Angular UI: all 4 steps render, no console errors
- [ ] All Phase 1 unit tests still pass
- [ ] No transcript content in any log output
- [ ] Default accuracy target is 90% (not 80%)

---

## Corrections Log
# Format: [YYYY-MM] What went wrong → Fix applied
