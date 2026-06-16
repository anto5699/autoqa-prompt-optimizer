# Playwright E2E Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Playwright in `frontend/`, configure it to auto-start both servers, and write three test files covering model-config UI, upload validation, and the full end-to-end optimization flow with real OpenAI calls.

**Architecture:** Playwright lives in `frontend/` alongside the Angular app. A `webServer` config auto-starts the FastAPI backend (port 8000) and Angular dev server (port 4200) before tests run. A committed fixture CSV (6 conversations, 1 rule) keeps test runs cheap; `max_iterations=1` and `accuracy_target=0.5` guarantee a fast finish.

**Tech Stack:** `@playwright/test`, `dotenv`, Chromium, Angular 17 dev server, FastAPI + uvicorn

---

## File Structure

```
frontend/
  playwright.config.ts            ← NEW: Playwright config with webServer + dotenv
  e2e/
    fixtures/
      test_conversations.csv      ← NEW: minimal 6-row fixture
    tests/
      upload-validation.spec.ts   ← NEW: form guards (no LLM calls)
      model-config.spec.ts        ← NEW: model config UI + real connection test
      optimization-flow.spec.ts   ← NEW: full pipeline with real OpenAI
  package.json                    ← MODIFY: add @playwright/test, dotenv, test:e2e script
```

---

## Task 1: Install Playwright dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install packages**

```bash
cd frontend
npm install -D @playwright/test dotenv
```

- [ ] **Step 2: Install Chromium browser**

```bash
cd frontend
npx playwright install chromium
```

- [ ] **Step 3: Add test script to package.json**

Open `frontend/package.json`. In the `"scripts"` section, add one line:

```json
"test:e2e": "playwright test"
```

- [ ] **Step 4: Verify playwright CLI works**

```bash
cd frontend
npx playwright --version
```

Expected output: `Version 1.x.x` (any recent version).

- [ ] **Step 5: Commit**

```bash
cd frontend
git add package.json package-lock.json
git commit -m "test: install @playwright/test for e2e suite"
```

---

## Task 2: Create `playwright.config.ts`

**Files:**
- Create: `frontend/playwright.config.ts`

- [ ] **Step 1: Create the config file**

Create `frontend/playwright.config.ts` with this exact content:

```typescript
import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Load OPENAI_API_KEY and OPENAI_MODEL from backend/.env
dotenv.config({ path: path.join(__dirname, '../backend/.env') });

export default defineConfig({
  testDir: './e2e/tests',
  timeout: 5 * 60 * 1000,        // 5 min per test — real LLM calls
  expect: { timeout: 30_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: 'http://localhost:4200',
    headless: true,
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      // Backend — start first so the proxy has a target
      command: './venv/bin/python -m uvicorn main:app --port 8000',
      cwd: path.join(__dirname, '../backend'),
      url: 'http://localhost:8000/health',
      reuseExistingServer: !process.env['CI'],
      timeout: 30_000,
      env: {
        OPENAI_API_KEY: process.env['OPENAI_API_KEY'] ?? '',
        OPENAI_MODEL: process.env['OPENAI_MODEL'] ?? 'gpt-4o',
      },
    },
    {
      // Angular dev server — starts after backend is ready
      command: 'npx ng serve --proxy-config proxy.conf.json --port 4200',
      url: 'http://localhost:4200',
      reuseExistingServer: !process.env['CI'],
      timeout: 90_000,
    },
  ],
});
```

- [ ] **Step 2: Verify config is valid**

```bash
cd frontend
npx playwright test --list
```

Expected: output lists zero tests and exits without error (no test files exist yet).

- [ ] **Step 3: Commit**

```bash
cd frontend
git add playwright.config.ts
git commit -m "test: add playwright.config.ts with auto-start webServer"
```

---

## Task 3: Create test fixture CSV

**Files:**
- Create: `frontend/e2e/fixtures/test_conversations.csv`

- [ ] **Step 1: Create directories**

```bash
mkdir -p frontend/e2e/fixtures frontend/e2e/tests
```

- [ ] **Step 2: Create the fixture CSV**

Create `frontend/e2e/fixtures/test_conversations.csv` with this exact content (6 rows, 1 rule, balanced 3 Yes / 3 No):

```csv
conversation_id,transcript,rule_id,rule_type,speaker,evaluation_type,n_messages,description,ground_truth
test_001,"[{""msg"":""Hello, thank you for calling ShopDirect. My name is Sarah, how can I help?"",""messageId"":1,""speaker"":""agent"",""timestamp"":1700000000},{""msg"":""Hi, I need help with my order."",""messageId"":2,""speaker"":""customer"",""timestamp"":1700000030}]",rule_answer_1,answer,agent,entire,0,,Yes
test_002,"[{""msg"":""Good morning! This is Alex from customer support. How can I assist you today?"",""messageId"":1,""speaker"":""agent"",""timestamp"":1700001000},{""msg"":""I have a billing question."",""messageId"":2,""speaker"":""customer"",""timestamp"":1700001030}]",rule_answer_1,answer,agent,entire,0,,Yes
test_003,"[{""msg"":""Welcome to ShopDirect support. My name is James. What can I do for you?"",""messageId"":1,""speaker"":""agent"",""timestamp"":1700002000},{""msg"":""I need to cancel my subscription."",""messageId"":2,""speaker"":""customer"",""timestamp"":1700002030}]",rule_answer_1,answer,agent,entire,0,,Yes
test_004,"[{""msg"":""Yeah, what do you need?"",""messageId"":1,""speaker"":""agent"",""timestamp"":1700003000},{""msg"":""I want to make a return."",""messageId"":2,""speaker"":""customer"",""timestamp"":1700003030}]",rule_answer_1,answer,agent,entire,0,,No
test_005,"[{""msg"":""Support."",""messageId"":1,""speaker"":""agent"",""timestamp"":1700004000},{""msg"":""I have a problem with my delivery."",""messageId"":2,""speaker"":""customer"",""timestamp"":1700004030}]",rule_answer_1,answer,agent,entire,0,,No
test_006,"[{""msg"":""Hold on a second."",""messageId"":1,""speaker"":""agent"",""timestamp"":1700005000},{""msg"":""I need to update my address."",""messageId"":2,""speaker"":""customer"",""timestamp"":1700005030}]",rule_answer_1,answer,agent,entire,0,,No
```

- [ ] **Step 3: Verify the CSV parses correctly**

```bash
cd backend
source venv/bin/activate
python - <<'EOF'
with open('../frontend/e2e/fixtures/test_conversations.csv', 'rb') as f:
    data = f.read()
from utils.csv_parser import parse
conversations, rules, gt_map, excluded = parse(data)
print(f"conversations={len(conversations)} rules={len(rules)} excluded={excluded}")
assert len(conversations) == 6
assert len(rules) == 1
assert excluded == []
print("OK")
EOF
```

Expected output:
```
conversations=6 rules=1 excluded=[]
OK
```

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/fixtures/test_conversations.csv
git commit -m "test: add minimal 6-conversation fixture CSV for e2e tests"
```

---

## Task 4: Write upload-validation tests

**Files:**
- Create: `frontend/e2e/tests/upload-validation.spec.ts`

- [ ] **Step 1: Create the test file**

Create `frontend/e2e/tests/upload-validation.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';
import path from 'path';

const FIXTURE = path.join(__dirname, '../fixtures/test_conversations.csv');

test.describe('Upload page validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
  });

  test('Start Optimization is disabled with no file selected', async ({ page }) => {
    const btn = page.getByRole('button', { name: /Start Optimization/i });
    await expect(btn).toBeDisabled();
  });

  test('Start Optimization becomes enabled after selecting a CSV file', async ({ page }) => {
    const btn = page.getByRole('button', { name: /Start Optimization/i });
    await expect(btn).toBeDisabled();

    await page.locator('input[type="file"]').setInputFiles(FIXTURE);

    await expect(btn).toBeEnabled();
  });

  test('max iterations input enforces min=1 max=10 via HTML attributes', async ({ page }) => {
    const iterationsInput = page.locator('input[type="number"]').first();
    await expect(iterationsInput).toHaveAttribute('min', '1');
    await expect(iterationsInput).toHaveAttribute('max', '10');
  });

  test('accuracy target input enforces min=0.1 max=1', async ({ page }) => {
    const accuracyInput = page.locator('input[type="number"]').last();
    await expect(accuracyInput).toHaveAttribute('min', '0.1');
    await expect(accuracyInput).toHaveAttribute('max', '1');
  });
});
```

- [ ] **Step 2: Run only this file to verify tests pass**

```bash
cd frontend
npx playwright test e2e/tests/upload-validation.spec.ts --headed=false
```

Expected: `4 passed`

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/tests/upload-validation.spec.ts
git commit -m "test: upload page validation e2e tests"
```

---

## Task 5: Write model-config tests

**Files:**
- Create: `frontend/e2e/tests/model-config.spec.ts`

- [ ] **Step 1: Create the test file**

Create `frontend/e2e/tests/model-config.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test.describe('Model configuration UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
  });

  test('model config section is visible with correct default values', async ({ page }) => {
    await expect(page.getByText('Model Configuration')).toBeVisible();

    const modelInput = page.locator('input[placeholder="gpt-4o"]');
    await expect(modelInput).toBeVisible();
    await expect(modelInput).toHaveValue('gpt-4o');

    await expect(page.locator('input[placeholder="sk-…"]')).toBeVisible();
    await expect(page.locator('input[placeholder="https://api.openai.com/v1"]')).toBeVisible();
    await expect(page.getByRole('button', { name: /Test Connection/i })).toBeVisible();
  });

  test('Test Connection shows success badge with valid API key', async ({ page }) => {
    const apiKey = process.env['OPENAI_API_KEY'];
    if (!apiKey) test.skip();

    await page.locator('input[placeholder="sk-…"]').fill(apiKey!);
    await page.getByRole('button', { name: /Test Connection/i }).click();

    await expect(page.locator('.conn-success')).toContainText('Connected', { timeout: 30_000 });
  });

  test('Test Connection button is enabled even with empty API key field', async ({ page }) => {
    // The backend falls back to the env key, so we only assert UI state here:
    // the button must not be disabled when the key field is empty.
    await page.locator('input[placeholder="sk-…"]').fill('');
    await expect(page.getByRole('button', { name: /Test Connection/i })).toBeEnabled();
  });

  test('Test Connection shows error with an invalid API key', async ({ page }) => {
    await page.locator('input[placeholder="sk-…"]').fill('sk-invalid-key-000000000000');

    await page.getByRole('button', { name: /Test Connection/i }).click();

    await expect(page.locator('.conn-error')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.conn-success')).not.toBeVisible();
  });
});
```

- [ ] **Step 2: Run only this file**

```bash
cd frontend
npx playwright test e2e/tests/model-config.spec.ts --headed=false
```

Expected: `4 passed` (test 2 skips if `OPENAI_API_KEY` is missing from `.env`).

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/tests/model-config.spec.ts
git commit -m "test: model config UI and connection validation e2e tests"
```

---

## Task 6: Write the full optimization-flow test

**Files:**
- Create: `frontend/e2e/tests/optimization-flow.spec.ts`

- [ ] **Step 1: Create the test file**

Create `frontend/e2e/tests/optimization-flow.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';
import path from 'path';

const FIXTURE = path.join(__dirname, '../fixtures/test_conversations.csv');

test('full optimization flow with real OpenAI', async ({ page }) => {
  const apiKey = process.env['OPENAI_API_KEY'];
  if (!apiKey) test.skip();

  // ── 1. Upload page ─────────────────────────────────────────────────────────
  await page.goto('/upload');
  await expect(page.getByRole('heading', { name: 'AutoQA Prompt Optimizer' })).toBeVisible();

  // ── 2. Fill model config ────────────────────────────────────────────────────
  await page.locator('input[placeholder="gpt-4o"]').fill('gpt-4o');
  await page.locator('input[placeholder="sk-…"]').fill(apiKey!);

  // ── 3. Verify connection ────────────────────────────────────────────────────
  await page.getByRole('button', { name: /Test Connection/i }).click();
  await expect(page.locator('.conn-success')).toContainText('Connected', { timeout: 30_000 });

  // ── 4. Upload fixture CSV ───────────────────────────────────────────────────
  await page.locator('input[type="file"]').setInputFiles(FIXTURE);

  // ── 5. Set minimal iterations so the test finishes quickly ──────────────────
  await page.locator('input[type="number"]').first().fill('1');   // max_iterations
  await page.locator('input[type="number"]').last().fill('0.5');  // accuracy_target

  // ── 6. Start optimization — lands on /descriptions/:id ─────────────────────
  await page.getByRole('button', { name: /Start Optimization/i }).click();
  await page.waitForURL(/\/descriptions\//, { timeout: 30_000 });
  await expect(page.getByRole('heading', { name: 'Define Parameter Descriptions' })).toBeVisible();

  // ── 7. Fill the description textarea(s) ────────────────────────────────────
  const textareas = page.locator('textarea');
  const count = await textareas.count();
  for (let i = 0; i < count; i++) {
    await textareas.nth(i).fill(
      'Evaluate whether the agent provided a warm, professional greeting that introduced themselves by name.'
    );
  }

  // ── 8. Submit descriptions — lands on /progress/:id ────────────────────────
  await page.getByRole('button', { name: /Start Optimization/i }).click();
  await page.waitForURL(/\/progress\//, { timeout: 30_000 });
  await expect(page.getByRole('heading', { name: 'Optimization in Progress' })).toBeVisible();

  // ── 9. Handle optional clarification step ──────────────────────────────────
  // The progress page may navigate to /clarification/:id if ambiguity is found.
  // We poll with a short timeout; if it doesn't happen, we continue waiting for results.
  try {
    await page.waitForURL(/\/clarification\//, { timeout: 25_000 });

    // Fill every clarification answer
    const clarifyAreas = page.locator('textarea');
    const clarifyCount = await clarifyAreas.count();
    for (let i = 0; i < clarifyCount; i++) {
      await clarifyAreas.nth(i).fill('No additional requirements. Evaluate as the description states.');
    }
    await page.getByRole('button', { name: /Submit & Continue/i }).click();
    await page.waitForURL(/\/progress\//, { timeout: 30_000 });
  } catch {
    // No clarification needed — already progressing toward results
  }

  // ── 10. Wait for optimization to complete and auto-navigate to /results/:id ─
  await page.waitForURL(/\/results\//, { timeout: 3 * 60 * 1000 });

  // ── 11. Assert results page content ────────────────────────────────────────
  await expect(page.getByRole('heading', { name: 'Optimization Results' })).toBeVisible();

  // Summary cards must be present
  const summaryCards = page.locator('.summary-card');
  await expect(summaryCards).toHaveCount(4);

  // Overall Accuracy card shows a percentage (e.g. "50.0%")
  const accuracyCard = summaryCards.nth(2);
  await expect(accuracyCard.locator('.lbl')).toContainText('Overall Accuracy');
  await expect(accuracyCard.locator('.val')).toContainText('%');

  // At least one parameter card must be rendered
  await expect(page.locator('.param-card')).toHaveCount(1);
});
```

- [ ] **Step 2: Run just this test (expect ~1-3 minutes)**

```bash
cd frontend
npx playwright test e2e/tests/optimization-flow.spec.ts --headed=false
```

Expected: `1 passed` (takes 1–3 min). If the test times out, check that the backend `.env` file has a valid `OPENAI_API_KEY`.

- [ ] **Step 3: Run the complete suite to confirm nothing interferes**

```bash
cd frontend
npm run test:e2e
```

Expected: `9 passed` (4 validation + 4 model-config + 1 flow).

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/tests/optimization-flow.spec.ts
git commit -m "test: full E2E optimization flow with real OpenAI calls"
```

---

## Running the tests

```bash
cd frontend
npm run test:e2e            # all tests, headless
npx playwright test --headed  # all tests, headed (watch browser)
npx playwright show-report    # open HTML report after a run
```

To run a single file:
```bash
npx playwright test e2e/tests/model-config.spec.ts
```
