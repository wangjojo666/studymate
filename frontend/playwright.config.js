import { defineConfig, devices } from "@playwright/test";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const e2eStorage = path.join(__dirname, ".e2e-storage");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const nodeCommand = process.platform === "win32" ? "node.exe" : "node";
const backendPort = 18080;
const frontendPort = 15173;
if (!process.env.TEST_WORKER_INDEX) {
  fs.rmSync(e2eStorage, { recursive: true, force: true });
}
fs.mkdirSync(e2eStorage, { recursive: true });

const backendEnv = {
  ...process.env,
  DATABASE_URL: `sqlite:///${path.join(e2eStorage, "studymate-e2e.db").replace(/\\/g, "/")}`,
  STORAGE_DIR: path.join(e2eStorage, "storage"),
  UPLOAD_DIR: path.join(e2eStorage, "storage", "uploads"),
  CHROMA_DIR: path.join(e2eStorage, "storage", "chroma"),
  TEXT_LLM_PROVIDER: "mock",
  TEXT_LLM_FALLBACK_PROVIDER: "none",
  OCR_LLM_PROVIDER: "mock",
  EMBEDDING_PROVIDER: "hash",
  RERANK_PROVIDER: "rule",
  CPP_RUN_ENABLED: "false",
  RATE_LIMIT_ENABLED: "false",
  APP_ENV: "development",
  ENABLE_DEMO_USER: "true",
  AUTH_SECRET_KEY: process.env.E2E_AUTH_SECRET_KEY || crypto.randomBytes(32).toString("hex"),
  E2E_BACKEND_PORT: String(backendPort)
};

const frontendEnv = {
  ...process.env,
  VITE_API_PROXY_TARGET: `http://127.0.0.1:${backendPort}`
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: [
    {
      command: `${nodeCommand} scripts/start-e2e-backend.mjs`,
      cwd: __dirname,
      env: backendEnv,
      url: `http://127.0.0.1:${backendPort}/api/health`,
      reuseExistingServer: false,
      timeout: 180_000
    },
    {
      command: `${npmCommand} run dev -- --port ${frontendPort}`,
      cwd: __dirname,
      env: frontendEnv,
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: false,
      timeout: 120_000
    }
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
