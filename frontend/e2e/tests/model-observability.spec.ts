import { test, expect, type Page } from '@playwright/test';
import path from 'path';

const FIXTURE = path.join(__dirname, '../fixtures/test_conversations.csv');

// Clear, unambiguous description → converges in 1 iteration at 70% target.
const ANSWER_DESC =
  "Evaluate whether the agent's very first message includes BOTH: " +
  "(1) a greeting phrase — 'hello', 'hi', 'good morning', 'good afternoon', or 'welcome' — " +
  "AND (2) the agent's own first name. Both must be present in that single opening message to Adhere.";

// ── helpers ───────────────────────────────────────────────────────────────────

async function pollUntilTerminal(page: Page, sessionId: string, limitMs: number): Promise<string> {
  return page.evaluate(
    async ({ sid, limit }: { sid: string; limit: number }) => {
      const end = Date.now() + limit;
      while (Date.now() < end) {
        try {
          const s = await fetch(`/api/sessions/${sid}`).then(r => r.json());
          if (s.current_phase === 'complete' || s.optimization_complete) return 'complete';
          if (s.current_phase === 'error') return `error: ${s.error_message ?? 'unknown'}`;
        } catch { /* transient — retry */ }
        await new Promise(r => setTimeout(r, 3_000));
      }
      return 'timeout';
    },
    { sid: sessionId, limit: limitMs },
  );
}

/**
 * Drives the upload → describe flow and lands on the progress page.
 * Returns the session ID extracted from the URL.
 */
async function startOptimizationFlow(page: Page): Promise<string> {
  await page.goto('/upload');

  // Default (.env) mode — uses server-side API key
  await page.getByRole('button', { name: /Test Connection/i }).click();
  await expect(page.locator('.conn-success')).toContainText('Connected', { timeout: 30_000 });

  await page.locator('input[type="file"]').setInputFiles(FIXTURE);

  // Set 1 iteration / 70% target so the run finishes quickly
  await page.evaluate(() => {
    const el = document.querySelector('app-upload');
    const ng = (window as any).ng;
    if (!el || !ng?.getComponent) return;
    const comp = ng.getComponent(el);
    comp.maxIterations = 1;
    comp.accuracyTarget = 0.70;
    ng.applyChanges(comp);
  });

  await page.locator('.cta-btn').click();
  await page.waitForURL(/\/descriptions\//, { timeout: 30_000 });

  // Wait for parameters to load on the descriptions page
  await page.waitForFunction(() => {
    const el = document.querySelector('app-descriptions');
    const ng = (window as any).ng;
    if (!el || !ng?.getComponent) return false;
    const comp = ng.getComponent(el);
    return comp?.parameters?.length > 0 && comp.loading === false;
  }, { timeout: 15_000 });

  // Fill all parameter descriptions and submit
  await page.evaluate((desc: string) => {
    const el = document.querySelector('app-descriptions');
    const ng = (window as any).ng;
    if (!el || !ng?.getComponent) return;
    const comp = ng.getComponent(el);
    Object.keys(comp.metricStates).forEach(key => {
      comp.metricStates[key].answerDescription = desc;
    });
    ng.applyChanges(comp);
    comp.submit();
  }, ANSWER_DESC);

  // May route via /clarification/ first if ambiguity detection fires questions
  await page.waitForURL(/\/(clarification|progress)\//, { timeout: 60_000 });

  if (page.url().includes('/clarification/')) {
    await page.waitForFunction(() => {
      const el = document.querySelector('app-clarification');
      const ng = (window as any).ng;
      if (!el || !ng?.getComponent) return false;
      const comp = ng.getComponent(el);
      return comp && !comp.loadingQuestions && comp.questions?.length > 0;
    }, { timeout: 30_000 });

    await page.evaluate(() => {
      const el = document.querySelector('app-clarification');
      const ng = (window as any).ng;
      if (!el || !ng?.getComponent) return;
      const comp = ng.getComponent(el);
      Object.keys(comp.answers).forEach(k => {
        comp.answers[k] = 'No additional requirements — evaluate exactly as the description states.';
      });
      ng.applyChanges(comp);
      comp.submit();
    });

    await page.waitForURL(/\/progress\//, { timeout: 30_000 });
  }

  const sessionId = page.url().match(/\/progress\/([^/?]+)/)?.[1] ?? '';
  expect(sessionId, 'Session ID must be extractable from the URL').toBeTruthy();
  return sessionId;
}

// ── tests ─────────────────────────────────────────────────────────────────────

test.describe('Model observability — banner, report chips, debug trace, print report', () => {
  // All tests in this suite perform real LLM calls.
  test.skip(!process.env['OPENAI_API_KEY'], 'Requires OPENAI_API_KEY');

  test('model banner — first progress log entry shows active evaluation and reasoning models', async ({ page }) => {
    const sessionId = await startOptimizationFlow(page);

    // The very first log-line must be the model banner emitted by csv_ingestion
    await expect(page.locator('.log-line').first()).toContainText('Evaluation model:', { timeout: 30_000 });
    await expect(page.locator('.log-line').first()).toContainText('Reasoning model:');

    // The banner should name a non-empty model string on both sides of the · separator
    const bannerText = await page.locator('.log-line').first().textContent();
    expect(bannerText).toMatch(/Evaluation model:\s*\S+/);
    expect(bannerText).toMatch(/Reasoning model:\s*\S+/);

    // Wait for run to complete before next test steps
    const phase = await pollUntilTerminal(page, sessionId, 8 * 60_000);
    expect(phase, `Run ended with: ${phase}`).toBe('complete');
  });

  test('results page — model chips and debug trace button visible after run completes', async ({ page }) => {
    const sessionId = await startOptimizationFlow(page);
    const phase = await pollUntilTerminal(page, sessionId, 8 * 60_000);
    expect(phase, `Run ended with: ${phase}`).toBe('complete');

    await page.goto(`/results/${sessionId}`);
    await expect(page.getByRole('heading', { name: 'Optimization Complete' })).toBeVisible({ timeout: 15_000 });

    // Evaluation model chip
    const evalChip = page.locator('.eval-chip');
    await expect(evalChip).toBeVisible();
    await expect(evalChip).toContainText('Evaluation:');
    // Must contain a non-trivial model name
    const evalText = await evalChip.textContent();
    expect(evalText?.replace('Evaluation:', '').trim().length).toBeGreaterThan(0);

    // Reasoning model chip
    const optChip = page.locator('.opt-chip');
    await expect(optChip).toBeVisible();
    await expect(optChip).toContainText('Reasoning:');
    const optText = await optChip.textContent();
    expect(optText?.replace('Reasoning:', '').trim().length).toBeGreaterThan(0);

    // Debug trace button must be present alongside the other export buttons
    await expect(page.getByRole('button', { name: /Debug Trace/i })).toBeVisible();
  });

  test('debug trace — /trace endpoint returns valid JSON with models_used and trace entries', async ({ page }) => {
    const sessionId = await startOptimizationFlow(page);
    const phase = await pollUntilTerminal(page, sessionId, 8 * 60_000);
    expect(phase, `Run ended with: ${phase}`).toBe('complete');

    // Fetch the trace endpoint directly within the page context (proxy routes /api → backend)
    const tracePayload = await page.evaluate(async (sid: string) => {
      const res = await fetch(`/api/sessions/${sid}/trace`);
      if (!res.ok) return null;
      return res.json();
    }, sessionId);

    expect(tracePayload).not.toBeNull();
    expect(tracePayload.session_id).toBe(sessionId);

    // models_used must contain both evaluator and optimizer keys
    expect(tracePayload.models_used).toBeDefined();
    expect(typeof tracePayload.models_used.evaluator).toBe('string');
    expect(tracePayload.models_used.evaluator.length).toBeGreaterThan(0);
    expect(typeof tracePayload.models_used.optimizer).toBe('string');
    expect(tracePayload.models_used.optimizer.length).toBeGreaterThan(0);

    // trace_log must be a non-empty array of structured entries
    expect(Array.isArray(tracePayload.trace_log)).toBeTruthy();
    expect(tracePayload.trace_log.length).toBeGreaterThan(0);

    const firstEntry = tracePayload.trace_log[0];
    expect(firstEntry).toHaveProperty('ts');
    expect(firstEntry).toHaveProperty('node');
    expect(firstEntry).toHaveProperty('model');
    expect(firstEntry).toHaveProperty('event');

    // Verify no transcript content leaked (spot-check: no 'transcript' or 'msg' keys at top level)
    for (const entry of tracePayload.trace_log) {
      expect(entry).not.toHaveProperty('transcript');
      expect(entry).not.toHaveProperty('msg');
      expect(entry).not.toHaveProperty('content');
    }
  });

  test('debug trace download — clicking button triggers file download named autoqa-trace-<sessionId>.json', async ({ page }) => {
    const sessionId = await startOptimizationFlow(page);
    const phase = await pollUntilTerminal(page, sessionId, 8 * 60_000);
    expect(phase, `Run ended with: ${phase}`).toBe('complete');

    await page.goto(`/results/${sessionId}`);
    await expect(page.getByRole('heading', { name: 'Optimization Complete' })).toBeVisible({ timeout: 15_000 });

    // Intercept the download event
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /Debug Trace/i }).click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe(`autoqa-trace-${sessionId}.json`);
  });

  test('print report — shows Evaluation model and Reasoning model rows', async ({ page }) => {
    const sessionId = await startOptimizationFlow(page);
    const phase = await pollUntilTerminal(page, sessionId, 8 * 60_000);
    expect(phase, `Run ended with: ${phase}`).toBe('complete');

    // Navigate to the print/PDF route
    await page.goto(`/results/${sessionId}/print`);

    // Wait for the report data to load (print report fetches data on init)
    await expect(page.getByText('Evaluation model')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Reasoning model')).toBeVisible();

    // Both model values must be non-empty text in the table
    const evalRow = page.locator('tr', { hasText: 'Evaluation model' });
    await expect(evalRow.locator('td').nth(1)).not.toBeEmpty();

    const reasoningRow = page.locator('tr', { hasText: 'Reasoning model' });
    await expect(reasoningRow.locator('td').nth(1)).not.toBeEmpty();
  });
});
