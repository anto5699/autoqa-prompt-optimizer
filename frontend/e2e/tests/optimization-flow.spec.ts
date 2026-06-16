import { test, expect, type Page } from '@playwright/test';
import path from 'path';

const FIXTURE = path.join(__dirname, '../fixtures/test_conversations.csv');

// Unambiguous description — achieves high accuracy so the test finishes in 1 iteration.
const ANSWER_DESC =
  "Evaluate whether the agent's very first message includes BOTH: " +
  "(1) a greeting phrase — 'hello', 'hi', 'good morning', 'good afternoon', or 'welcome' — " +
  "AND (2) the agent's own first name. Both must be present in that single opening message to Adhere.";

// ── helpers ──────────────────────────────────────────────────────────────────

/** Poll GET /api/sessions/:id until the graph reaches a terminal state. */
async function pollUntilTerminal(page: Page, sessionId: string, limitMs: number): Promise<string> {
  return page.evaluate(
    async ({ sid, limit }: { sid: string; limit: number }) => {
      const end = Date.now() + limit;
      while (Date.now() < end) {
        try {
          const s = await fetch(`/api/sessions/${sid}`).then(r => r.json());
          if (s.current_phase === 'complete' || s.optimization_complete)
            return 'complete';
          if (s.current_phase === 'error')
            return `error: ${s.error_message ?? 'unknown'}`;
        } catch { /* transient network glitch — retry */ }
        await new Promise(r => setTimeout(r, 3_000));
      }
      return 'timeout';
    },
    { sid: sessionId, limit: limitMs },
  );
}

// ── test ──────────────────────────────────────────────────────────────────────

test('full optimization flow — upload → describe → [clarify] → progress → results', async ({ page }) => {
  if (!process.env['OPENAI_API_KEY']) test.skip();

  // ── 1. Upload page ───────────────────────────────────────────────────────
  await page.goto('/upload');
  await expect(page.getByRole('heading', { name: 'Upload Evaluation Data' })).toBeVisible();

  // ── 2. Model config — Default (.env) mode (uses server-side API key) ─────
  await expect(page.getByRole('button', { name: 'Default (.env)' })).toHaveClass(/active/);

  // ── 3. Verify the backend key is valid ───────────────────────────────────
  await page.getByRole('button', { name: /Test Connection/i }).click();
  await expect(page.locator('.conn-success')).toContainText('Connected', { timeout: 30_000 });

  // ── 4. Upload fixture CSV ────────────────────────────────────────────────
  await page.locator('input[type="file"]').setInputFiles(FIXTURE);
  await expect(page.locator('.drop-file-name')).toContainText('test_conversations.csv');

  // ── 5. Set run config via Angular component API (more reliable than DOM events) ──
  await page.evaluate(() => {
    const el = document.querySelector('app-upload');
    const ng = (window as any).ng;
    if (!el || !ng?.getComponent) return;
    const comp = ng.getComponent(el);
    comp.maxIterations = 1;     // finish fast
    comp.accuracyTarget = 0.70; // easy target
    ng.applyChanges(comp);
  });
  await expect(page.locator('input[type="range"]')).toHaveValue('1');
  await expect(page.getByRole('button', { name: '70%' })).toHaveClass(/active/);

  // ── 6. Start — lands on /descriptions/:id ───────────────────────────────
  await page.locator('.cta-btn').click();
  await page.waitForURL(/\/descriptions\//, { timeout: 30_000 });
  await expect(page.getByRole('heading', { name: 'Configure Evaluation Parameters' })).toBeVisible();

  // ── 7. Wait for parameters to load ──────────────────────────────────────
  await page.waitForFunction(() => {
    const el = document.querySelector('app-descriptions');
    const ng = (window as any).ng;
    if (!el || !ng?.getComponent) return false;
    const comp = ng.getComponent(el);
    return comp?.parameters?.length > 0 && comp.loading === false;
  }, { timeout: 15_000 });

  // ── 8. Fill answer descriptions and submit ───────────────────────────────
  await page.evaluate((desc: string) => {
    const el = document.querySelector('app-descriptions');
    const ng = (window as any).ng;
    if (!el || !ng?.getComponent) return;
    const comp = ng.getComponent(el);
    Object.keys(comp.metricStates).forEach(key => {
      comp.metricStates[key].answerDescription = desc;
      // triggerDescription left empty — all parameters are static in the fixture
    });
    ng.applyChanges(comp);
    comp.submit();
  }, ANSWER_DESC);

  // Descriptions component waits for ambiguity detection, then routes to
  // /clarification if questions were found, or /progress if none.
  await page.waitForURL(/\/(clarification|progress)\//, { timeout: 60_000 });
  const firstUrl = page.url();
  const sessionId = firstUrl.match(/\/(clarification|progress)\/([^/?]+)/)?.[2] ?? '';

  // ── 9. Clarification branch — if routed there directly from describe ──────
  if (firstUrl.includes('/clarification/')) {
    // Questions are guaranteed present — component does a single fetch
    await page.waitForFunction(() => {
      const el = document.querySelector('app-clarification');
      const ng = (window as any).ng;
      if (!el || !ng?.getComponent) return false;
      const comp = ng.getComponent(el);
      return comp && comp.loadingQuestions === false && comp.questions?.length > 0;
    }, { timeout: 30_000 });

    await expect(page.locator('.question-card').first()).toBeVisible();

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

  // ── 10. Progress page — visible ──────────────────────────────────────────
  await expect(page.getByRole('heading', { name: 'Optimization Running' })).toBeVisible();

  // ── 11. Poll until graph reaches complete (max 8 min) ────────────────────
  const finalPhase = await pollUntilTerminal(page, sessionId, 8 * 60_000);
  expect(finalPhase, `Run ended with: ${finalPhase}`).toBe('complete');

  // ── 12. Results page ─────────────────────────────────────────────────────
  await page.goto(`/results/${sessionId}`);

  // Report loads inside *ngIf="report" so the heading appearing means data is ready
  await expect(page.getByRole('heading', { name: 'Optimization Complete' })).toBeVisible({ timeout: 15_000 });

  // KPI grid — 4 cards
  const kpiCards = page.locator('.kpi-card');
  await expect(kpiCards).toHaveCount(4);
  await expect(kpiCards.nth(0).locator('.kpi-label')).toContainText('Overall Accuracy');
  await expect(kpiCards.nth(0).locator('.kpi-val')).toContainText('%');
  await expect(kpiCards.nth(1).locator('.kpi-label')).toContainText('Met Target');
  await expect(kpiCards.nth(2).locator('.kpi-label')).toContainText('Iterations');
  await expect(kpiCards.nth(3).locator('.kpi-label')).toContainText('Conversations');

  // 1 static metric → 1 parameter card
  const paramCards = page.locator('.param-card');
  await expect(paramCards).toHaveCount(1);
  await expect(paramCards.first().locator('.param-id')).toContainText('Greeting Compliance');
  await expect(paramCards.first().locator('.status-badge')).toBeVisible();
  await expect(paramCards.first().locator('.acc-journey')).toContainText('%');

  // Expand the parameter card and verify before/after prompts and confusion matrix
  await paramCards.first().locator('.param-row').click();
  const compareCols = page.locator('.compare-col');
  await expect(compareCols).toHaveCount(2);
  await expect(compareCols.nth(0).locator('.compare-label')).toContainText('Before');
  await expect(compareCols.nth(1).locator('.compare-label')).toContainText('After');
  await expect(page.locator('.prompt-pre').first()).not.toBeEmpty();
  await expect(page.locator('.prompt-pre.after')).not.toBeEmpty();

  await expect(page.locator('.matrix-grid')).toBeVisible();
  await expect(page.locator('.cell-tp')).toContainText('True Pos');
  await expect(page.locator('.cell-tn')).toContainText('True Neg');

  // Conversation-level results expandable
  await page.locator('.convs-toggle').click();
  const convRows = page.locator('.conv-table tbody tr');
  await expect(convRows).toHaveCount(10); // 10 conversations in fixture

  // Export CSV button present and functional
  await expect(page.getByRole('button', { name: /Export CSV/i })).toBeVisible();
});
