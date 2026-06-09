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
