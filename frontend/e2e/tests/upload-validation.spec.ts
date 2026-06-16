import { test, expect } from '@playwright/test';
import path from 'path';

const FIXTURE = path.join(__dirname, '../fixtures/test_conversations.csv');

test.describe('Upload page validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
  });

  test('Start Optimization is disabled with no file selected', async ({ page }) => {
    await expect(page.locator('.cta-btn')).toBeDisabled();
  });

  test('Start Optimization becomes enabled after selecting a CSV file', async ({ page }) => {
    await expect(page.locator('.cta-btn')).toBeDisabled();
    await page.locator('input[type="file"]').setInputFiles(FIXTURE);
    await expect(page.locator('.cta-btn')).toBeEnabled();
  });

  test('max iterations slider has min=1 max=10', async ({ page }) => {
    const slider = page.locator('input[type="range"]');
    await expect(slider).toHaveAttribute('min', '1');
    await expect(slider).toHaveAttribute('max', '10');
    await expect(slider).toHaveValue('8'); // default
  });

  test('accuracy target has four preset buttons and defaults to 90%', async ({ page }) => {
    for (const label of ['70%', '80%', '90%', '95%']) {
      await expect(page.getByRole('button', { name: label })).toBeVisible();
    }
    await expect(page.getByRole('button', { name: '90%' })).toHaveClass(/active/);
  });

  test('clicking an accuracy target button marks it active', async ({ page }) => {
    await page.getByRole('button', { name: '70%' }).click();
    await expect(page.getByRole('button', { name: '70%' })).toHaveClass(/active/);
    await expect(page.getByRole('button', { name: '90%' })).not.toHaveClass(/active/);
  });

  test('CSV format panel toggles open and closed', async ({ page }) => {
    const toggle = page.getByRole('button', { name: /View expected CSV format/i });
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.locator('.format-panel')).toBeVisible();
    await expect(page.getByRole('button', { name: /Hide expected CSV format/i })).toBeVisible();
    await page.getByRole('button', { name: /Hide expected CSV format/i }).click();
    await expect(page.locator('.format-panel')).not.toBeVisible();
  });
});
