import { test, expect } from '@playwright/test';

// ── Locked state (no API key required) ────────────────────────────────────────

test.describe('Dual model configuration — locked state', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
  });

  test('model rows carry models-locked class before test connection', async ({ page }) => {
    await expect(page.locator('.model-rows')).toHaveClass(/models-locked/);
  });

  test('hint text is visible before test connection', async ({ page }) => {
    await expect(page.locator('.models-hint')).toBeVisible();
    await expect(page.locator('.models-hint')).toContainText(
      'Test connection above to unlock model selection',
    );
  });

  test('Evaluation Model input is disabled before test connection', async ({ page }) => {
    // When no models loaded (pre-connection), an <input> is rendered instead of <select>
    const evalInput = page.locator('.model-rows .model-row').nth(0).locator('input[type="text"]');
    await expect(evalInput).toBeDisabled();
  });

  test('Reasoning Model input is disabled before test connection', async ({ page }) => {
    const reasoningInput = page.locator('.model-rows .model-row').nth(1).locator('input[type="text"]');
    await expect(reasoningInput).toBeDisabled();
  });

  test('Evaluation Model label and caption are present', async ({ page }) => {
    await expect(page.getByText('Evaluation Model')).toBeVisible();
    await expect(
      page.getByText('Applied to conversations — use your planned production model'),
    ).toBeVisible();
  });

  test('Reasoning Model label and caption are present', async ({ page }) => {
    // exact: true avoids matching the "Use different endpoint for Reasoning Model" checkbox label
    await expect(page.getByText('Reasoning Model', { exact: true })).toBeVisible();
    await expect(
      page.getByText('Used for prompt optimization, RCA & analysis'),
    ).toBeVisible();
  });
});

// ── Unlocked state (requires valid API key) ───────────────────────────────────

test.describe('Dual model configuration — after successful test connection', () => {
  test.beforeEach(async ({ page }) => {
    if (!process.env['OPENAI_API_KEY']) test.skip();
    await page.goto('/upload');
    await page.getByRole('button', { name: /Test Connection/i }).click();
    await expect(page.locator('.conn-success')).toContainText('Connected', { timeout: 30_000 });
  });

  test('models-locked class is removed after connection', async ({ page }) => {
    await expect(page.locator('.model-rows')).not.toHaveClass(/models-locked/);
  });

  test('hint text disappears after connection', async ({ page }) => {
    await expect(page.locator('.models-hint')).not.toBeVisible();
  });

  test('both model dropdowns appear and are enabled after connection', async ({ page }) => {
    const selects = page.locator('.model-rows select');
    await expect(selects).toHaveCount(2);
    await expect(selects.nth(0)).toBeEnabled();
    await expect(selects.nth(1)).toBeEnabled();
  });

  test('Evaluation Model dropdown is populated with at least one model', async ({ page }) => {
    const evalSelect = page.locator('.model-rows select').nth(0);
    const options = await evalSelect.locator('option').allTextContents();
    expect(options.length).toBeGreaterThanOrEqual(1);
    // Each option should look like a model name (non-empty)
    expect(options.every(o => o.trim().length > 0)).toBeTruthy();
  });

  test('Reasoning Model dropdown is populated with at least one model', async ({ page }) => {
    const reasoningSelect = page.locator('.model-rows select').nth(1);
    const options = await reasoningSelect.locator('option').allTextContents();
    expect(options.length).toBeGreaterThanOrEqual(1);
  });

  test('selecting Evaluation Model does not remove Reasoning Model dropdown', async ({ page }) => {
    const evalSelect = page.locator('.model-rows select').nth(0);
    const reasoningSelect = page.locator('.model-rows select').nth(1);

    // Interact with the evaluation model dropdown
    const options = await evalSelect.locator('option').allTextContents();
    const pickIdx = options.length > 1 ? 1 : 0;
    await evalSelect.selectOption({ index: pickIdx });

    // Reasoning model dropdown must still exist and be interactive
    await expect(reasoningSelect).toBeVisible();
    await expect(reasoningSelect).toBeEnabled();
  });

  test('selecting Reasoning Model does not affect Evaluation Model dropdown', async ({ page }) => {
    const evalSelect = page.locator('.model-rows select').nth(0);
    const reasoningSelect = page.locator('.model-rows select').nth(1);

    const evalValueBefore = await evalSelect.inputValue();

    const options = await reasoningSelect.locator('option').allTextContents();
    const pickIdx = options.length > 1 ? options.length - 1 : 0;
    await reasoningSelect.selectOption({ index: pickIdx });

    // Evaluation model dropdown value is unchanged
    await expect(evalSelect).toBeVisible();
    await expect(evalSelect).toBeEnabled();
    await expect(evalSelect).toHaveValue(evalValueBefore);
  });

  test('Evaluation and Reasoning dropdowns can be set to different models', async ({ page }) => {
    const evalSelect = page.locator('.model-rows select').nth(0);
    const reasoningSelect = page.locator('.model-rows select').nth(1);

    const evalOptions = await evalSelect.locator('option').allTextContents();
    const reasoningOptions = await reasoningSelect.locator('option').allTextContents();

    if (evalOptions.length < 2 || reasoningOptions.length < 2) test.skip();

    await evalSelect.selectOption({ index: 0 });
    await reasoningSelect.selectOption({ index: reasoningOptions.length - 1 });

    const evalVal = await evalSelect.inputValue();
    const reasoningVal = await reasoningSelect.inputValue();

    // Both are set (non-empty) and can differ
    expect(evalVal.trim().length).toBeGreaterThan(0);
    expect(reasoningVal.trim().length).toBeGreaterThan(0);
  });
});

// ── Custom optimizer endpoint panel ───────────────────────────────────────────

test.describe('Dual model configuration — custom optimizer endpoint toggle', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
  });

  test('"Use different endpoint" checkbox is unchecked by default', async ({ page }) => {
    const checkbox = page.locator('input[type="checkbox"]').first();
    await expect(checkbox).not.toBeChecked();
  });

  test('"Use different endpoint" toggle reveals the opt-panel', async ({ page }) => {
    await expect(page.locator('.opt-panel')).not.toBeVisible();
    await page.locator('input[type="checkbox"]').first().click();
    await expect(page.locator('.opt-panel')).toBeVisible();
  });

  test('opt-panel has Custom Key and Custom Endpoint mode tabs', async ({ page }) => {
    await page.locator('input[type="checkbox"]').first().click();
    // Scope to .opt-panel — "Custom Endpoint" also appears in the main model config mode tabs
    await expect(page.locator('.opt-panel').getByRole('button', { name: 'Custom Key' })).toBeVisible();
    await expect(page.locator('.opt-panel').getByRole('button', { name: 'Custom Endpoint' })).toBeVisible();
  });

  test('Custom Key tab shows Reasoning API Key field only, no Base URL', async ({ page }) => {
    await page.locator('input[type="checkbox"]').first().click();
    await page.locator('.opt-panel').getByRole('button', { name: 'Custom Key' }).click();

    await expect(page.locator('.opt-panel input[placeholder="sk-…"]')).toBeVisible();
    await expect(
      page.locator('.opt-panel input[placeholder="https://api.openai.com/v1"]'),
    ).not.toBeVisible();
  });

  test('Custom Endpoint tab shows both API Key and Base URL fields', async ({ page }) => {
    await page.locator('input[type="checkbox"]').first().click();
    await page.locator('.opt-panel').getByRole('button', { name: 'Custom Endpoint' }).click();

    await expect(page.locator('.opt-panel input[placeholder="sk-…"]')).toBeVisible();
    await expect(
      page.locator('.opt-panel input[placeholder="https://api.openai.com/v1"]'),
    ).toBeVisible();
  });

  test('unchecking "Use different endpoint" hides the opt-panel again', async ({ page }) => {
    const checkbox = page.locator('input[type="checkbox"]').first();
    await checkbox.click();
    await expect(page.locator('.opt-panel')).toBeVisible();
    await checkbox.click();
    await expect(page.locator('.opt-panel')).not.toBeVisible();
  });
});
