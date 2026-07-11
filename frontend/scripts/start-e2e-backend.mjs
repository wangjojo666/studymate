import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const repoDir = path.resolve(frontendDir, "..");
const backendDir = path.join(repoDir, "backend");
const venvDir = process.env.E2E_BACKEND_VENV
  ? path.resolve(process.env.E2E_BACKEND_VENV)
  : path.join(backendDir, ".venv-e2e");
const venvPython = process.platform === "win32"
  ? path.join(venvDir, "Scripts", "python.exe")
  : path.join(venvDir, "bin", "python");
const requirementsPath = path.join(backendDir, "requirements.txt");
const markerPath = path.join(venvDir, ".studymate-e2e-ready.json");
const prepareOnly = process.argv.includes("--prepare");
const backendPort = parseBackendPort(process.env.E2E_BACKEND_PORT || "18080");

const backendPython = resolveBackendPython();

if (prepareOnly) {
  process.exit(0);
}

const server = spawn(
  backendPython,
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)],
  {
    cwd: backendDir,
    env: process.env,
    stdio: "inherit"
  }
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    server.kill(signal);
  });
}

server.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

function ensureBackendVenv() {
  if (!fs.existsSync(venvPython)) {
    const bootstrapPython = findBootstrapPython();
    runChecked(
      bootstrapPython.command,
      [...bootstrapPython.args, "-m", "venv", venvDir],
      { cwd: repoDir }
    );
  }

  const marker = readJson(markerPath);
  const requirementsMtimeMs = fs.statSync(requirementsPath).mtimeMs;
  if (marker?.requirementsMtimeMs === requirementsMtimeMs) {
    return;
  }

  runChecked(venvPython, ["-m", "pip", "install", "-r", requirementsPath], {
    cwd: backendDir
  });

  fs.writeFileSync(
    markerPath,
    JSON.stringify({ requirementsMtimeMs }, null, 2),
    "utf-8"
  );
}

function resolveBackendPython() {
  if (process.env.E2E_BACKEND_PYTHON) {
    return process.env.E2E_BACKEND_PYTHON;
  }

  const projectVenvPython = process.platform === "win32"
    ? path.join(backendDir, ".venv", "Scripts", "python.exe")
    : path.join(backendDir, ".venv", "bin", "python");

  if (fs.existsSync(projectVenvPython) && canImportBackend(projectVenvPython)) {
    return projectVenvPython;
  }

  ensureBackendVenv();
  return venvPython;
}

function findBootstrapPython() {
  if (process.env.E2E_BOOTSTRAP_PYTHON) {
    const candidate = { command: process.env.E2E_BOOTSTRAP_PYTHON, args: [] };
    if (isSupportedPython(candidate)) {
      return candidate;
    }
    throw new Error("E2E_BOOTSTRAP_PYTHON must point to Python 3.11 or 3.12.");
  }

  const candidates = process.platform === "win32"
    ? [
        { command: "python", args: [] },
        { command: "py", args: ["-3.12"] },
        { command: "py", args: ["-3.11"] },
        { command: "python3", args: [] },
        { command: "py", args: ["-3"] }
      ]
    : [
        { command: "python3", args: [] },
        { command: "python", args: [] }
      ];

  for (const candidate of candidates) {
    if (isSupportedPython(candidate)) {
      return candidate;
    }
  }

  throw new Error("Python 3.11 or 3.12 is required to prepare the E2E backend virtualenv.");
}

function runChecked(command, args, options = {}) {
  const result = spawnSync(command, args, {
    ...options,
    stdio: "inherit"
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}`);
  }
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return null;
  }
}

function canImportBackend(pythonPath) {
  const result = spawnSync(
    pythonPath,
    ["-c", "import fastapi, uvicorn, sqlalchemy, alembic"],
    { cwd: backendDir, stdio: "ignore" }
  );
  return result.status === 0;
}

function isSupportedPython(candidate) {
  const result = spawnSync(
    candidate.command,
    [
      ...candidate.args,
      "-c",
      "import sys; raise SystemExit(0 if (sys.version_info[:2] >= (3, 11) and sys.version_info[:2] < (3, 13)) else 1)"
    ],
    { stdio: "ignore" }
  );
  return result.status === 0;
}

function parseBackendPort(value) {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("E2E_BACKEND_PORT must be an integer between 1 and 65535.");
  }
  return port;
}
