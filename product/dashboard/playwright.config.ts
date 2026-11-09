import { defineConfig } from "@playwright/test";

// End to end tests (phase 4 design section 9) against the running stack, seeded with
// `make demo-seed-offline`. Run with `make e2e` (inside the Playwright Docker image).
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.DASHBOARD_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
