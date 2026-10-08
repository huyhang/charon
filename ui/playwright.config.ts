import { defineConfig, devices } from "@playwright/test";

// Specs that change settings every other spec relies on.
const SHARED_SETTINGS = /settings\.spec\.ts/;

// Runs against an already running `make ui-dev` (UI + Charon + fake Download Station).
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: process.env.UI_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] }, testIgnore: SHARED_SETTINGS },
    // Changes settings every other test relies on (e.g. TMDB's token), so it runs after them.
    {
      name: "settings",
      use: { ...devices["Desktop Chrome"] },
      testMatch: SHARED_SETTINGS,
      dependencies: ["chromium"],
    },
  ],
});
