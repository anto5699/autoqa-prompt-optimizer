import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Load OPENAI_API_KEY and OPENAI_MODEL from backend/.env
dotenv.config({ path: path.join(__dirname, '../backend/.env') });

export default defineConfig({
  testDir: './e2e/tests',
  timeout: 5 * 60 * 1000,        // 5 min per test — real LLM calls
  expect: { timeout: 30_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: 'http://localhost:4200',
    headless: true,
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      // Backend — start first so the proxy has a target
      command: './venv/bin/python -m uvicorn main:app --port 8000',
      cwd: path.join(__dirname, '../backend'),
      url: 'http://localhost:8000/health',
      reuseExistingServer: !process.env['CI'],
      timeout: 30_000,
      env: {
        OPENAI_API_KEY: process.env['OPENAI_API_KEY'] ?? '',
        OPENAI_MODEL: process.env['OPENAI_MODEL'] ?? 'gpt-4o',
      },
    },
    {
      // Angular dev server — starts after backend is ready
      command: 'npx ng serve --proxy-config proxy.conf.json --port 4200',
      url: 'http://localhost:4200',
      reuseExistingServer: !process.env['CI'],
      timeout: 90_000,
    },
  ],
});
