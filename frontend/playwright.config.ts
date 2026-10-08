import { defineConfig } from "@playwright/test";

// Smoke tests run against the Vite dev server, which proxies /api to the Python backend.
// Start the backend first: PYTHONPATH=src python -m idx_evidence_lab.web_app
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:5173" },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173/app/",
    reuseExistingServer: true,
  },
});
