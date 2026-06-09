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
