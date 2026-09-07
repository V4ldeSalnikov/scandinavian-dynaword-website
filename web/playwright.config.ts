import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  timeout: 90000,
  expect: { timeout: 20000 },
  workers: 1,
  use: {
    reducedMotion: "reduce",
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  outputDir: "../.cache/browser-tests",
  reporter: "list",
});
