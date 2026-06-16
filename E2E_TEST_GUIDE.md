# E2E Functional Test Guide — Two New Features

## What Was Added

### Feature 1: Continue Optimization
When an optimization run hits `max_iterations` with some parameters still below target, the results page now shows a **"Continue Optimization"** panel. Clicking it creates a new session seeded from the existing one's unconverged parameters (with full iteration history carried forward) and navigates to that session's progress page.

**New backend endpoint:** `POST /api/sessions/{session_id}/continue`  
Request body: `{ "additional_iterations": 1–10 }`  
Response: `{ "new_session_id": "...", "parameters_continuing": ["rule_id", ...] }`

### Feature 2: Export PDF Report
The results page now has an **"Export PDF"** button next to "Export CSV". It opens `/results/{sessionId}/print` in a new tab, which renders a fully expanded, print-optimised report and auto-triggers `window.print()` after 600ms.

The PDF includes:
- Cover page (session metadata)
- Overall accuracy, precision, and recall (macro averages — new fields in the API)
- Description updates overview table (all parameters: initial → final accuracy, delta, status)
- Per-parameter: metrics, confusion matrix, SVG accuracy trend chart, before/after prompt diff
- RCA + recommendations for every unconverged (`max_iterations_reached`) parameter

**New fields in `GET /api/sessions/{id}/report` response:**
```json
{
  "summary": {
    "overall_precision": 0.82,
    "overall_recall": 0.78,
    ...existing fields unchanged...
  }
}
```

---

## Starting the App

```bash
# Terminal 1 — Backend
cd autoqa-prompt-optimizer/backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd autoqa-prompt-optimizer/frontend
ng serve --proxy-config proxy.conf.json
# App runs at http://localhost:4200
```

---

## E2E Test Flows

### Flow A — Continue Optimization (happy path)

**Goal:** Run an optimization that deliberately hits `max_iterations` before all parameters converge, then continue with the unconverged ones.

**Steps:**

1. Upload a CSV and set `max_iterations = 1` (forces early termination).
2. Submit descriptions and let optimization run to completion.
3. Navigate to `/results/{sessionId}`.
4. **Assert:** The amber "Continue Optimization" panel is visible (`[class="continue-panel"]`).
5. **Assert:** Unconverged parameter names appear as chips inside `.continue-chips code`.
6. **Assert:** The additional iterations input defaults to `5` (`input.iter-input` has value `"5"`).
7. Change iterations to `2`.
8. Click the "Continue Optimization" button (`.continue-btn`).
9. **Assert:** Button enters disabled/loading state (`Starting…`).
10. **Assert:** Browser navigates to `/progress/{new_session_id}` (a different session ID than the original).
11. Wait for the new session to reach `complete` phase.
12. Navigate to `/results/{new_session_id}`.
13. **Assert:** Report loads. Parameters shown are only the ones that were unconverged in the original run.
14. **Assert:** Iteration history for those parameters contains entries from the continuation run.

**API shortcut (no UI):** You can also test via curl after a completed session with `parameters_below_target` non-empty:
```bash
curl -s -X POST http://localhost:8000/api/sessions/{SESSION_ID}/continue \
  -H "Content-Type: application/json" \
  -d '{"additional_iterations": 2}'
# Expect 201 with { "new_session_id": "...", "parameters_continuing": [...] }
```

**Error cases to cover:**
| Scenario | Expected HTTP status |
|---|---|
| Session does not exist | 404 |
| Session not yet complete | 409 |
| All parameters already converged | 409 |
| `additional_iterations` = 0 or 11 | 400 |

---

### Flow B — Continue Optimization panel hidden when all converged

1. Run an optimization that converges all parameters within `max_iterations`.
2. Navigate to `/results/{sessionId}`.
3. **Assert:** The `.continue-panel` element is NOT present in the DOM.

---

### Flow C — Export PDF button opens print view

1. Run any optimization to completion and navigate to `/results/{sessionId}`.
2. **Assert:** The "↗ Export PDF" button (`button.pdf-btn`) is visible in the page header.
3. Click the Export PDF button.
4. **Assert:** A new tab/window opens at `/results/{sessionId}/print`.
5. In the new tab, wait for `.print-root` to appear (report loaded).
6. **Assert:** `.print-cover` is visible (cover page rendered).
7. **Assert:** `.print-kpi-row` contains 4 KPI cards (Accuracy, Precision, Recall, Parameters Met Target).
8. **Assert:** The "Description Updates Overview" table (`table.print-table`) has one row per parameter.
9. **Assert:** At least one `.print-param-block` exists per parameter.
10. **Assert (for unconverged params):** `.print-rca-block` is present inside the param block.
11. **Assert (for converged params):** `.print-rca-block` is NOT present inside the param block.

**Note on `window.print()`:** Playwright intercepts the print dialog automatically. You can assert it was called by listening for the `page.on('dialog', ...)` event or by simply checking the DOM is rendered correctly before 600ms fires.

---

### Flow D — New `overall_precision` and `overall_recall` fields in API response

After any completed optimization:
```bash
curl -s http://localhost:8000/api/sessions/{SESSION_ID}/report | jq '.summary | {overall_accuracy, overall_precision, overall_recall}'
```
**Assert:** All three fields are present and are numbers between 0.0 and 1.0.

---

### Flow E — Backward compatibility (existing flows unchanged)

Verify none of the existing functionality regressed:

1. **CSV upload → descriptions → (optional clarification) → progress → results** — full flow works end-to-end.
2. **"↓ Export CSV"** button still works and downloads a `.csv` file.
3. **Session status polling** (`GET /api/sessions/{id}`) returns the same shape as before.
4. **SSE streaming** (`GET /api/sessions/{id}/stream`) still emits `progress` and `complete` events.
5. **Report structure** — all pre-existing fields in `GET /api/sessions/{id}/report` are still present; the only addition is `overall_precision` and `overall_recall` in `summary`.

---

## Playwright Selector Reference

| Element | Selector |
|---|---|
| Continue Optimization panel | `.continue-panel` |
| Unconverged param chips | `.continue-chips code` |
| Iterations input | `input.iter-input` |
| Continue button | `button.continue-btn` |
| Export PDF button | `button.pdf-btn` |
| Print report root | `.print-root` |
| Print cover page | `.print-cover` |
| Print KPI row | `.print-kpi-row` |
| Print description table | `table.print-table` |
| Per-parameter print block | `.print-param-block` |
| RCA block in print | `.print-rca-block` |
| Print loading message | `.print-loading` |

---

## Existing Playwright Config

```bash
cd autoqa-prompt-optimizer/frontend
npx playwright test                        # run all e2e tests
npx playwright test --headed               # with browser visible
npx playwright test e2e/tests/optimization-flow.spec.ts  # existing flow test
```

The existing `optimization-flow.spec.ts` covers the core upload → optimize → results flow and should still pass unchanged.
