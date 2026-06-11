import { test, expect } from '@playwright/test';

test.describe('Model configuration UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
  });

  test('model config section shows 3 mode tabs and defaults to Default (.env)', async ({ page }) => {
    await expect(page.getByText('Model Configuration')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Default (.env)' })).toHaveClass(/active/);
    await expect(page.getByRole('button', { name: 'Custom OpenAI Key' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Custom Endpoint' })).toBeVisible();
  });

  test('Default mode hides API key field', async ({ page }) => {
    await expect(page.locator('input[placeholder="sk-…"]')).not.toBeVisible();
  });

  test('Custom OpenAI Key mode shows API key field, hides base URL', async ({ page }) => {
    await page.getByRole('button', { name: 'Custom OpenAI Key' }).click();
    await expect(page.locator('input[placeholder="sk-…"]')).toBeVisible();
    await expect(page.locator('input[placeholder="https://api.openai.com/v1"]')).not.toBeVisible();
  });

  test('Custom Endpoint mode shows both API key and base URL fields', async ({ page }) => {
    await page.getByRole('button', { name: 'Custom Endpoint' }).click();
    await expect(page.locator('input[placeholder="sk-…"]')).toBeVisible();
    await expect(page.locator('input[placeholder="https://api.openai.com/v1"]')).toBeVisible();
  });

  test('model field shows text input before test connection', async ({ page }) => {
    await expect(page.locator('input[placeholder="gpt-4o"]')).toBeVisible();
    await expect(page.locator('select')).not.toBeVisible();
  });

  test('Test Connection is enabled on all modes', async ({ page }) => {
    for (const mode of ['Default (.env)', 'Custom OpenAI Key', 'Custom Endpoint']) {
      await page.getByRole('button', { name: mode }).click();
      await expect(page.getByRole('button', { name: /Test Connection/i })).toBeEnabled();
    }
  });

  test('Test Connection shows success and model dropdown with valid key', async ({ page }) => {
    const apiKey = process.env['OPENAI_API_KEY'];
    if (!apiKey) test.skip();

    await page.getByRole('button', { name: 'Custom OpenAI Key' }).click();
    await page.locator('input[placeholder="sk-…"]').fill(apiKey!);
    await page.getByRole('button', { name: /Test Connection/i }).click();

    await expect(page.locator('.conn-success')).toContainText('Connected', { timeout: 30_000 });
    await expect(page.locator('select')).toBeVisible();
  });

  test('Test Connection shows error badge with invalid API key', async ({ page }) => {
    await page.getByRole('button', { name: 'Custom OpenAI Key' }).click();
    await page.locator('input[placeholder="sk-…"]').fill('sk-invalid-key-000000000000');
    await page.getByRole('button', { name: /Test Connection/i }).click();

    await expect(page.locator('.conn-error')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.conn-success')).not.toBeVisible();
  });
});
