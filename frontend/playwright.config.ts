import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 1,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  timeout: 30_000,

  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  /* Dev server를 자동 시작 (frontend만, backend는 별도 실행 필요) */
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 30_000,
  },

  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
