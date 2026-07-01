import { test, expect } from '@playwright/test';

const FAKE_SESSION_ID = 'cccccccc-dddd-eeee-ffff-000000000001';

const BASE_SESSION = {
  session_id: FAKE_SESSION_ID,
  current_phase: 'evaluating',
  current_iteration: 1,
  parameters: [],
  clarifying_questions: [],
  parameter_summary: {},
  progress_log: ['Iteration 1: evaluating 79 conversations…'],
  error_message: null,
  node_progress: null,
};

async function mockStream(page: import('@playwright/test').Page, sessionId: string) {
  await page.route(`/api/sessions/${sessionId}/stream`, route =>
    route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
      body: '',
    })
  );
}

test.describe('Node progress bar', () => {
  test('Progress bar is hidden when node_progress is null', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({ status: 200, json: { ...BASE_SESSION, node_progress: null } })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);
    await page.waitForTimeout(500);

    await expect(page.locator('.node-progress-card')).not.toBeVisible();
  });

  test('Progress bar is hidden when total <= 1', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({
        status: 200,
        json: {
          ...BASE_SESSION,
          node_progress: { node: 'evaluating', step: 1, total: 1 },
        },
      })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);
    await page.waitForTimeout(500);

    await expect(page.locator('.node-progress-card')).not.toBeVisible();
  });

  test('Progress bar appears with correct step and total from polling', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({
        status: 200,
        json: {
          ...BASE_SESSION,
          node_progress: { node: 'evaluating', step: 42, total: 79 },
        },
      })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);

    await expect(page.locator('.node-progress-card')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.node-progress-label')).toContainText('42 / 79');
    await expect(page.locator('.node-progress-pct')).toContainText('53%');
  });

  test('Progress bar fill width reflects percentage', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({
        status: 200,
        json: {
          ...BASE_SESSION,
          node_progress: { node: 'evaluating', step: 79, total: 79 },
        },
      })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);

    await expect(page.locator('.node-progress-card')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.node-progress-pct')).toContainText('100%');

    const fill = page.locator('.node-progress-fill');
    const style = await fill.getAttribute('style');
    expect(style).toContain('100');
  });

  test('Progress bar updates when SSE heartbeat delivers new node_progress', async ({ page }) => {
    let resolveStream!: () => void;
    const streamReady = new Promise<void>(r => { resolveStream = r; });

    await page.route(`/api/sessions/${FAKE_SESSION_ID}/stream`, async route => {
      resolveStream();
      const encoder = new TextEncoder();
      const body = encoder.encode(
        'event: progress\ndata: {"phase":"evaluating","message":null,"timestamp":"2026-01-01T00:00:00Z","node_progress":{"node":"evaluating","step":10,"total":79}}\n\n'
      );
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: Buffer.from(body),
      });
    });

    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({
        status: 200,
        json: { ...BASE_SESSION, node_progress: null },
      })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);

    // The SSE event with node_progress should make the bar appear
    await expect(page.locator('.node-progress-card')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.node-progress-label')).toContainText('10 / 79');
  });

  test('Progress bar shows for optimizer phase', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({
        status: 200,
        json: {
          ...BASE_SESSION,
          current_phase: 'optimizing_prompts',
          node_progress: { node: 'optimizing_prompts', step: 3, total: 8 },
        },
      })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);

    await expect(page.locator('.node-progress-card')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.node-progress-label')).toContainText('3 / 8');
    await expect(page.locator('.node-progress-pct')).toContainText('38%');
  });
});
