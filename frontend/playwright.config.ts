import { defineConfig, devices } from '@playwright/test'

const FRONTEND_PORT = 5174
const BACKEND_PORT = 8010

// Default E2E harness (restored from Parent A at integration, 2026-10): starts the real
// backend on a throwaway *_test database (e2e/start-backend.sh) and the Vite dev server on
// dedicated ports, seeds one clinic through the public API (e2e/global-setup.ts), and runs
// every spec except the deployed-stack pilot UAT, which has its own config:
// playwright.uat.config.ts (Parent B's harness, against docker-compose.e2e.yml).
export default defineConfig({
  testDir: './e2e',
  testIgnore: 'uat.spec.ts',
  globalSetup: './e2e/global-setup.ts',
  // One worker, no retries: the backend rate-limits logins per IP, and a retry
  // would hide a real failure while spending that budget.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'pt-PT',
    timezoneId: 'Europe/Lisbon',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // Resets the dedicated *_test database, migrates it, then serves the real API.
      command: 'bash e2e/start-backend.sh',
      url: `http://127.0.0.1:${BACKEND_PORT}/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { E2E_BACKEND_PORT: String(BACKEND_PORT), E2E_FRONTEND_PORT: String(FRONTEND_PORT) },
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      timeout: 60_000,
      reuseExistingServer: false,
      env: { VITE_PROXY_TARGET: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
})
