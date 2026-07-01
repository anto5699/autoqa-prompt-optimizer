import { test, expect } from '@playwright/test';

const FAKE_SESSION_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const NEW_SESSION_ID  = 'ffffffff-0000-1111-2222-333333333333';

const ERROR_SESSION_NO_DATA = {
  session_id: FAKE_SESSION_ID,
  current_phase: 'error',
  current_iteration: 0,
  parameters: [],
  clarifying_questions: [],
  parameter_summary: {},
  progress_log: ['Iteration 0: evaluating 10 conversations…'],
  error_message: 'Request timed out.',
};

const ERROR_SESSION_WITH_DATA = {
  ...ERROR_SESSION_NO_DATA,
  current_iteration: 1,
  parameter_summary: {
    greeting_compliance: { accuracy: 0.75, status: 'optimizing', rca_findings: null },
    empathy_score:       { accuracy: 0.60, status: 'optimizing', rca_findings: null },
    call_closure:        { accuracy: 0.92, status: 'converged',  rca_findings: null },
  },
};

// Suppress SSE stream — return an empty event stream that never closes
async function mockStream(page: import('@playwright/test').Page, sessionId: string) {
  await page.route(`/api/sessions/${sessionId}/stream`, route =>
    route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
      body: '',
    })
  );
}

test.describe('Resume from error', () => {
  test('Resume button is hidden when no accuracy data exists (error before first benchmark)', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({ status: 200, json: ERROR_SESSION_NO_DATA })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);

    // Error card should appear
    await expect(page.locator('.error-card')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.error-card-title')).toContainText('Optimization failed');
    await expect(page.locator('.error-card-body')).toContainText('Request timed out.');

    // Start Over is present, Resume is absent (no accuracy data)
    await expect(page.locator('.btn-start-over')).toBeVisible();
    await expect(page.locator('.btn-resume')).not.toBeVisible();
  });

  test('Resume button is visible when at least one iteration has accuracy data', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({ status: 200, json: ERROR_SESSION_WITH_DATA })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);

    await expect(page.locator('.error-card')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.btn-resume')).toBeVisible();
    await expect(page.locator('.btn-resume')).toContainText('Resume');
    await expect(page.locator('.btn-start-over')).toBeVisible();
  });

  test('Resume navigates to new session progress page', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({ status: 200, json: ERROR_SESSION_WITH_DATA })
    );

    // Mock the continue endpoint
    await page.route(`/api/sessions/${FAKE_SESSION_ID}/continue`, route =>
      route.fulfill({
        status: 201,
        json: {
          new_session_id: NEW_SESSION_ID,
          parameters_continuing: ['greeting_compliance', 'empathy_score'],
        },
      })
    );

    // Mock the new session so the progress page doesn't 404
    await mockStream(page, NEW_SESSION_ID);
    await page.route(`/api/sessions/${NEW_SESSION_ID}`, route =>
      route.fulfill({
        status: 200,
        json: {
          session_id: NEW_SESSION_ID,
          current_phase: 'evaluating',
          current_iteration: 0,
          parameters: [],
          clarifying_questions: [],
          parameter_summary: {},
          progress_log: ['Continuation from previous session — 2 unconverged parameter(s)'],
          error_message: null,
        },
      })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);
    await expect(page.locator('.btn-resume')).toBeVisible({ timeout: 10_000 });

    await page.locator('.btn-resume').click();

    // Should navigate to the new session's progress page
    await expect(page).toHaveURL(`/progress/${NEW_SESSION_ID}`, { timeout: 10_000 });
    await expect(page.getByRole('heading', { name: 'Optimization Running' })).toBeVisible();
  });

  test('Resume button is disabled while request is in flight', async ({ page }) => {
    await mockStream(page, FAKE_SESSION_ID);
    await page.route(`/api/sessions/${FAKE_SESSION_ID}`, route =>
      route.fulfill({ status: 200, json: ERROR_SESSION_WITH_DATA })
    );

    // Delay the continue response so we can observe the disabled state
    await page.route(`/api/sessions/${FAKE_SESSION_ID}/continue`, async route => {
      await new Promise(r => setTimeout(r, 2_000));
      await route.fulfill({
        status: 201,
        json: { new_session_id: NEW_SESSION_ID, parameters_continuing: [] },
      });
    });
    await mockStream(page, NEW_SESSION_ID);
    await page.route(`/api/sessions/${NEW_SESSION_ID}`, route =>
      route.fulfill({ status: 200, json: { ...ERROR_SESSION_NO_DATA, session_id: NEW_SESSION_ID, current_phase: 'evaluating', error_message: null } })
    );

    await page.goto(`/progress/${FAKE_SESSION_ID}`);
    await expect(page.locator('.btn-resume')).toBeVisible({ timeout: 10_000 });

    await page.locator('.btn-resume').click();

    // Button should show "Resuming…" and be disabled while the request is pending
    await expect(page.locator('.btn-resume')).toBeDisabled();
    await expect(page.locator('.btn-resume')).toContainText('Resuming');
  });
});
