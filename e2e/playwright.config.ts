import { defineConfig } from "@playwright/test";

// End-to-end workflows (PRD Appendix B). Point these at a running stack:
//   E2E_API_URL       FastAPI base URL (default http://127.0.0.1:8000), started with
//                     ENVIRONMENT=development ALLOW_DEMO_AUTH=true (see backend/.env.demo.example)
//   E2E_DEMO_USER_ID  a disposable Clerk-style id, e.g. user_e2e_<timestamp>; its rows are deleted at the end
//   E2E_WEB_URL       Next.js URL for the UI smoke tests (default http://localhost:3000)
export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: process.env.E2E_WEB_URL || "http://localhost:3000", trace: "retain-on-failure" },
});
