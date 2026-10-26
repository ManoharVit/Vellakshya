import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright Configuration for Vellakshya PDF Workstation.
 * Covers Web E2E, API testing, Accessibility (axe-core), and Visual Regression.
 */
export default defineConfig({
  testDir: './tests',
  testMatch: /.*\.(spec|test)\.(js|ts|mjs)/,
  timeout: 30 * 1000,
  expect: {
    timeout: 5000,
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'Desktop Chromium',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /(e2e|api|accessibility|pdf-validation)\/.*\.spec\.(js|ts)/,
    },
    {
      name: 'Mobile Viewport Emulation',
      use: { ...devices['Pixel 5'] },
      testMatch: /e2e\/.*\.spec\.(js|ts)/,
    },
  ],
  webServer: {
    command: 'sh -c "([ -f .venv/bin/uvicorn ] && PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000) || (python3 -m pip install -q -r requirements.txt 2>/dev/null; PYTHONPATH=. python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000)"',
    url: 'http://127.0.0.1:8000',
    reuseExistingServer: true,
    timeout: 30 * 1000,
  },
});
