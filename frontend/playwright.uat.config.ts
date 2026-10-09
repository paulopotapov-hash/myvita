import { defineConfig, devices } from '@playwright/test'

// Pilot UAT (Parent B's harness): runs e2e/uat.spec.ts against an already-running stack
// seeded with backend/scripts/seed_staging.py (e.g. docker-compose.e2e.yml), never against a
// developer's servers. Usage:
//   E2E_BASE_URL=http://127.0.0.1:18083 SEED_PASSWORD=... npx playwright test -c playwright.uat.config.ts
// The default config (playwright.config.ts) runs every other spec on a local throwaway stack.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'uat.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: 'line',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:15173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
  },
})
