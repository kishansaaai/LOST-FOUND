import { defineConfig } from "@playwright/test";

// Runs against a live stack seeded with `make seed` (demo accounts, password Passw0rd!demo).
export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure", screenshot: "only-on-failure" },
});
