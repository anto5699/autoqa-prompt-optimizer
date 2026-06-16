# Playwright E2E Test Suite — AutoQA Prompt Optimizer

**Date:** 2026-06-09
**Scope:** End-to-end Playwright tests covering model config UI and the full optimization flow, using real OpenAI API calls.

---

## Goals

- Verify the newly added model configuration fields (model, API key, base URL) render and behave correctly
- Validate the Test Connection flow returns a success badge with a real API call
- Exercise the complete optimization pipeline: upload → descriptions → progress → results
- Run with one command, no manual server management

---

## Infrastructure

### Installation
`@playwright/test` installed as a dev dependency in `frontend/`.

### Location
```
frontend/
  playwright.config.ts
  e2e/
    fixtures/
      test_conversations.csv    ← committed fixture, 5 conversations, 1 rule
    tests/
      model-config.spec.ts
      optimization-flow.spec.ts
      upload-validation.spec.ts
```

### `playwright.config.ts`

- `baseURL: 'http://localhost:4200'`
- `timeout: 5 * 60 * 1000` (5 min per test — real LLM calls)
- `expect.timeout: 30_000`
- `use: { headless: true, video: 'retain-on-failure', screenshot: 'only-on-failure' }`
- `webServer` array (ordered — backend starts first):
  1. `cd ../backend && ./venv/bin/python -m uvicorn main:app --port 8000`  
     → waits for `http://localhost:8000/health`
  2. `ng serve --proxy-config proxy.conf.json --port 4200`  
     → waits for `http://localhost:4200`
  - `reuseExistingServer: !process.env.CI` (reuse in dev, always fresh in CI)
- API key loaded from `backend/.env` via `dotenv` and injected into `process.env` before webServer starts

### npm script
`"test:e2e": "playwright test"` added to `frontend/package.json`

---

## Test Data

**File:** `frontend/e2e/fixtures/test_conversations.csv`

- Generated from `generate_demo_csv.py` with 5 conversations
- 1 answer rule (no trigger — simpler evaluation)
- ~3 Yes, ~2 No ground truth labels
- Max iterations for E2E run: **1** (fast finish)
- Accuracy target for E2E run: **0.5** (always satisfiable with 1 rule)

---

## Test Files

### `model-config.spec.ts`

| # | Scenario | Key assertion |
|---|----------|---------------|
| 1 | Model config section visible | "Model", "API Key", "Base URL" labels present; model input defaults to `gpt-4o` |
| 2 | Test Connection — valid key | Badge text matches `/Connected · gpt-4o/i` |
| 3 | Test Connection — empty API key | Error message visible (not success badge) |
| 4 | Start Optimization disabled without CSV | Button has `disabled` attribute before file is selected |

### `optimization-flow.spec.ts`

Full happy path (~1–3 min with real OpenAI):

| Step | Action | Assertion |
|------|--------|-----------|
| 1 | Navigate to `/upload` | Page title "AutoQA Prompt Optimizer" visible |
| 2 | Fill model config (from env) | Fields populated |
| 3 | Click Test Connection | Success badge visible |
| 4 | Upload `test_conversations.csv` | File name shown in dropzone |
| 5 | Set max_iterations=1, accuracy_target=0.5 | Fields updated |
| 6 | Click Start Optimization | Navigates to `/descriptions/:id` |
| 7 | Fill one description per parameter | Text areas filled |
| 8 | Click Submit | Navigates to `/progress/:id` |
| 9 | Wait for "complete" phase | Phase label shows "Complete" (up to 3 min) |
| 10 | Auto-navigate to `/results/:id` | URL matches `/results/` |
| 11 | Assert summary card | At least 1 parameter shown, overall accuracy is a number |

### `upload-validation.spec.ts`

| # | Scenario | Key assertion |
|---|----------|---------------|
| 1 | No file → button disabled | `Start Optimization` has `disabled` attribute |
| 2 | File selected → button enabled | `disabled` attribute removed |
| 3 | Max iterations input respects min/max | HTML `min="1" max="10"` attributes present |

---

## API Key Handling

- Read from `backend/.env` using `dotenv` in `playwright.config.ts`
- Set as `process.env.OPENAI_API_KEY` so tests can access via `process.env`
- Never hardcoded; `.env` is gitignored

---

## Run Instructions

```bash
cd frontend
npm install          # installs @playwright/test
npx playwright install chromium
npm run test:e2e     # starts both servers, runs all tests
```

To run a single file:
```bash
npx playwright test e2e/tests/model-config.spec.ts
```

To run headed (watch mode):
```bash
npx playwright test --headed
```
