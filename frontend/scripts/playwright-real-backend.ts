import { spawn, type ChildProcess } from "node:child_process";
import { mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../..", import.meta.url));
const backendRoot = join(repositoryRoot, "backend");
const python = join(repositoryRoot, ".venv", "Scripts", "python.exe");
const runtimeRoot = join(tmpdir(), "shravya-playwright-real-journey");
const databasePath = join(runtimeRoot, "shravya-playwright.sqlite");
const mediaRoot = join(runtimeRoot, "audio");
const backendPort = 8011;

export const realBackendApiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`;

const backendEnvironment: NodeJS.ProcessEnv = {
  ...process.env,
  SHRAVYA_DATABASE_URL: `sqlite:///${databasePath.replaceAll("\\", "/")}`,
  SHRAVYA_MEDIA_ROOT: mediaRoot,
  SHRAVYA_CORS_ORIGINS: "http://127.0.0.1:4173",
};

function commandFailure(label: string, output: string) {
  const safeOutput = output.trim().slice(-4000) || "No process output was captured.";
  return new Error(`${label} failed.\n${safeOutput}`);
}

function runBackendCommand(args: string[], label: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(python, args, {
      cwd: backendRoot,
      env: backendEnvironment,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let output = "";
    child.stdout?.on("data", (chunk: Buffer) => { output += chunk.toString(); });
    child.stderr?.on("data", (chunk: Buffer) => { output += chunk.toString(); });
    child.once("error", (error) => reject(commandFailure(label, error.message)));
    child.once("exit", (code) => code === 0 ? resolve() : reject(commandFailure(label, output)));
  });
}

async function waitForBackend(process: ChildProcess, output: () => string): Promise<void> {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (process.exitCode !== null) throw commandFailure("Real backend startup", output());
    try {
      const response = await fetch(`http://127.0.0.1:${backendPort}/openapi.json`);
      if (response.ok) return;
    } catch {
      // The server is still starting; wait briefly without relying on a fixed sleep in tests.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw commandFailure("Real backend startup", output());
}

async function stopProcess(process: ChildProcess): Promise<void> {
  if (process.exitCode !== null) return;
  const exited = new Promise<void>((resolve) => process.once("exit", () => resolve()));
  process.kill("SIGTERM");
  await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 3000))]);
  if (process.exitCode === null) {
    process.kill("SIGKILL");
    await exited;
  }
}

async function removeRuntime(): Promise<void> {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    try {
      await rm(runtimeRoot, { force: true, recursive: true, maxRetries: 0 });
      return;
    } catch (error) {
      if (attempt === 9) throw error;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
}

export async function resetRealDemo(): Promise<void> {
  await runBackendCommand(["-m", "scripts.seed_photosynthesis_demo", "--reset"], "Deterministic demo reset");
}

export async function prepareRealBackend(): Promise<{ stop: () => Promise<void> }> {
  await removeRuntime();
  await mkdir(mediaRoot, { recursive: true });
  await runBackendCommand(["-m", "alembic", "upgrade", "head"], "Real backend migration");
  await resetRealDemo();

  const process = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)], {
    cwd: backendRoot,
    env: backendEnvironment,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  let output = "";
  process.stdout?.on("data", (chunk: Buffer) => { output += chunk.toString(); });
  process.stderr?.on("data", (chunk: Buffer) => { output += chunk.toString(); });

  try {
    await waitForBackend(process, () => output);
  } catch (error) {
    await stopProcess(process);
    throw error;
  }

  return {
    stop: async () => {
      await stopProcess(process);
      await removeRuntime();
    },
  };
}
