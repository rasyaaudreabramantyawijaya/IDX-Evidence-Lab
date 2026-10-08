import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Backend (python -m idx_evidence_lab.web_app) listens on 127.0.0.1:5500 by default.
const api = process.env.VITE_API_TARGET ?? "http://127.0.0.1:5500";

export default defineConfig({
  plugins: [react()],
  // Built files are meant to be served by the backend under /app/ (not wired yet, see frontend/README.md).
  base: "/app/",
  server: {
    port: 5173,
    // Same-origin in dev, so the backend's CORS rules and security headers behave as in production.
    proxy: { "/api": { target: api, changeOrigin: false } },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    // Emit external JS/CSS only: no inline script or style, so the strict CSP can be enforced.
    assetsInlineLimit: 0,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
