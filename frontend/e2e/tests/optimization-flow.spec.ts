import { test, expect } from '@playwright/test';
import path from 'path';

const FIXTURE = path.join(__dirname, '../fixtures/test_conversations.csv');

test('full optimization flow with real OpenAI', async ({ page }) => {
  const apiKey = process.env['OPENAI_API_KEY'];
  if (!apiKey) test.skip();

  // ── 1. Upload page ─────────────────────────────────────────────────────────
  await page.goto('/upload');
  await expect(page.getByRole('heading', { name: 'AutoQA Prompt Optimizer' })).toBeVisible();

  // ── 2. Set model config via Angular component API (fill() is unreliable with ngModel) ──
  await page.evaluate((key) => {
    const appEl = document.querySelector('app-upload');
    const ng = (window as any).ng;
    if (!appEl || !ng?.getComponent) return;
    const comp = ng.getComponent(appEl);
    if (!comp?.modelConfig) return;
    comp.modelConfig.model = 'gpt-4o';
    comp.modelConfig.apiKey = key;
    ng.applyChanges(comp);
  }, apiKey!);

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

  // ── 7+8. Fill descriptions and submit via Angular component API ────────────
  // Angular's [(ngModel)] binding is unreliable with Playwright fill() —
  // use ng.getComponent (available in dev-mode ng serve) to set state directly.
  // Wait for getSession() to complete (rules loaded) before setting descriptions.
  await page.waitForFunction(() => {
    const appEl = document.querySelector('app-descriptions');
    const ng = (window as any).ng;
    if (!appEl || !ng?.getComponent) return false;
    const comp = ng.getComponent(appEl);
    return comp?.rules?.length > 0 && !comp.loading;
  }, { timeout: 15_000 });

  await page.evaluate((desc) => {
    const appEl = document.querySelector('app-descriptions');
    const ng = (window as any).ng;
    if (!appEl || !ng?.getComponent) return;
    const comp = ng.getComponent(appEl);
    if (!comp?.descriptions) return;
    Object.keys(comp.descriptions).forEach(k => { comp.descriptions[k] = desc; });
    comp.submit();
  }, "Evaluate whether the agent's first message includes their own first name and a greeting phrase (hello, hi, good morning, good afternoon, or welcome).");

  await page.waitForURL(/\/progress\//, { timeout: 30_000 });
  await expect(page.getByRole('heading', { name: 'Optimization in Progress' })).toBeVisible();

  // ── 9+10. Poll backend directly until complete (SSE can drop in headless) ──
  const sessionId = page.url().split('/progress/')[1];

  const finalPhase = await page.evaluate(
    async ({ sid, deadline }: { sid: string; deadline: number }) => {
      while (Date.now() < deadline) {
        try {
          const r = await fetch(`/api/sessions/${sid}`);
          const s = await r.json();
          if (s.current_phase === 'awaiting_clarification' && s.clarifying_questions?.length) {
            return 'clarification';
          }
          if (s.optimization_complete || s.current_phase === 'complete') return 'complete';
          if (s.current_phase === 'error') return 'error';
        } catch { /* retry on network glitch */ }
        await new Promise(res => setTimeout(res, 3000));
      }
      return 'timeout';
    },
    { sid: sessionId, deadline: Date.now() + 8 * 60 * 1000 }
  );

  if (finalPhase === 'clarification') {
    await page.goto(`/clarification/${sessionId}`);

    await page.waitForFunction(() => {
      const appEl = document.querySelector('app-clarification');
      const ng = (window as any).ng;
      if (!appEl || !ng?.getComponent) return false;
      const comp = ng.getComponent(appEl);
      return comp?.questions?.length > 0 && Object.keys(comp.answers).length > 0;
    }, { timeout: 15_000 });

    await page.evaluate((answer) => {
      const appEl = document.querySelector('app-clarification');
      const ng = (window as any).ng;
      if (!appEl || !ng?.getComponent) return;
      const comp = ng.getComponent(appEl);
      if (!comp?.answers) return;
      Object.keys(comp.answers).forEach(k => { comp.answers[k] = answer; });
      comp.submit();
    }, 'No additional requirements. Evaluate as the description states.');

    const afterClarify = await page.evaluate(
      async ({ sid, deadline }: { sid: string; deadline: number }) => {
        while (Date.now() < deadline) {
          try {
            const r = await fetch(`/api/sessions/${sid}`);
            const s = await r.json();
            if (s.optimization_complete || s.current_phase === 'complete') return 'complete';
            if (s.current_phase === 'error') return 'error';
          } catch { /* retry */ }
          await new Promise(res => setTimeout(res, 3000));
        }
        return 'timeout';
      },
      { sid: sessionId, deadline: Date.now() + 8 * 60 * 1000 }
    );
    expect(afterClarify).toBe('complete');
  } else {
    expect(finalPhase).toBe('complete');
  }

  await page.goto(`/results/${sessionId}`);

  // ── 11. Assert results page content ────────────────────────────────────────
  await expect(page.getByRole('heading', { name: 'Optimization Results' })).toBeVisible();

  const summaryCards = page.locator('.summary-card');
  await expect(summaryCards).toHaveCount(4);

  const accuracyCard = summaryCards.nth(2);
  await expect(accuracyCard.locator('.lbl')).toContainText('Overall Accuracy');
  await expect(accuracyCard.locator('.val')).toContainText('%');

  await expect(page.locator('.param-card')).toHaveCount(1);
});
