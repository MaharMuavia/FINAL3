import { spawn, execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const DEFAULT_API_URL = 'http://localhost:8000/api';
const DEFAULT_FRONTEND_HOST = '127.0.0.1';
const DEFAULT_FRONTEND_PORT = '3000';
const STARTUP_TIMEOUT_MS = 120_000;

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const defaultFrontendDir = path.resolve(scriptDir, '..');

function normalizeUrl(value) {
  return (value || DEFAULT_API_URL).replace(/\/+$/, '');
}

function resolvePython(repoRoot, platform) {
  const venvPython = platform === 'win32'
    ? path.join(repoRoot, '.venv', 'Scripts', 'python.exe')
    : path.join(repoRoot, '.venv', 'bin', 'python');

  return existsSync(venvPython) ? venvPython : 'python';
}

function parseBackendTarget(apiUrl) {
  const parsed = new URL(apiUrl);
  return {
    host: parsed.hostname || '127.0.0.1',
    port: Number(parsed.port || (parsed.protocol === 'https:' ? 443 : 80)),
  };
}

function healthUrlFor(apiUrl) {
  return new URL('/health/live', apiUrl).toString();
}

function apiOriginFor(apiUrl) {
  const parsed = new URL(apiUrl);
  if (parsed.pathname.replace(/\/+$/, '') === '/api') {
    parsed.pathname = '/';
    parsed.search = '';
    parsed.hash = '';
  }
  return parsed.toString().replace(/\/+$/, '');
}

export function createDevPlan({
  frontendDir = defaultFrontendDir,
  env = process.env,
  platform = process.platform,
  nodePath = process.execPath,
} = {}) {
  const repoRoot = path.resolve(frontendDir, '..');
  const apiUrl = normalizeUrl(env.NEXT_PUBLIC_DATAVERSE_API_URL);
  const apiOrigin = apiOriginFor(apiUrl);
  const nextBin = path.join(frontendDir, 'node_modules', 'next', 'dist', 'bin', 'next');

  return {
    apiUrl,
    apiOrigin,
    healthUrl: healthUrlFor(apiOrigin),
    backendTarget: parseBackendTarget(apiOrigin),
    backend: {
      command: resolvePython(repoRoot, platform),
      args: [
        '-m',
        'uvicorn',
        'app.main:app',
        '--app-dir',
        'dataverse_backend',
        '--host',
        '127.0.0.1',
        '--port',
        '8000',
        '--reload',
        '--reload-dir',
        'dataverse_backend',
      ],
      cwd: repoRoot,
    },
    frontend: {
      command: nodePath,
      args: [
        nextBin,
        'dev',
        '--hostname',
        env.NEXT_FRONTEND_HOST || DEFAULT_FRONTEND_HOST,
        '--port',
        env.NEXT_FRONTEND_PORT || DEFAULT_FRONTEND_PORT,
      ],
      cwd: frontendDir,
    },
  };
}

function isPortOpen(host, port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    socket.setTimeout(1_000);
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.once('error', () => resolve(false));
  });
}

async function waitForPort(host, port, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isPortOpen(host, port)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  return false;
}

export async function waitForBackendHealth(apiUrl, timeoutMs, fetchImpl = fetch) {
  const healthUrl = healthUrlFor(apiUrl);
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetchImpl(healthUrl, { cache: 'no-store' });
      if (response.ok) {
        return true;
      }
    } catch {
      // Backend process may still be importing modules.
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  return false;
}

function startProcess(label, processPlan, env = process.env) {
  const child = spawn(processPlan.command, processPlan.args, {
    cwd: processPlan.cwd,
    env,
    stdio: 'inherit',
    shell: false,
    windowsHide: false,
  });

  child.once('exit', (code, signal) => {
    if (code !== 0 && signal !== 'SIGTERM') {
      console.error(`[dev] ${label} exited with code ${code ?? signal}`);
    }
  });

  return child;
}

export function isMainModule(moduleUrl, argvPath) {
  return Boolean(argvPath) && moduleUrl === pathToFileURL(argvPath).href;
}

function killPort(port) {
  try {
    if (process.platform === 'win32') {
      const output = execSync('netstat -ano').toString();
      const lines = output.split('\n');
      for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 5 && parts[1].includes(`:${port}`)) {
          const pid = parts[parts.length - 1];
          if (pid && pid !== '0') {
            console.log(`[dev] Stopping existing process (PID ${pid}) on port ${port}...`);
            execSync(`taskkill /F /PID ${pid}`);
            return true;
          }
        }
      }
    } else {
      try {
        const pid = execSync(`lsof -t -i:${port}`).toString().trim();
        if (pid) {
          console.log(`[dev] Stopping existing process (PID ${pid}) on port ${port}...`);
          execSync(`kill -9 ${pid}`);
          return true;
        }
      } catch (e) {
        // Fallback for systems without lsof
        const pid = execSync(`fuser ${port}/tcp 2>/dev/null`).toString().trim();
        if (pid) {
          console.log(`[dev] Stopping existing process (PID ${pid}) on port ${port}...`);
          execSync(`kill -9 ${pid}`);
          return true;
        }
      }
    }
  } catch (error) {
    // Ignore error
  }
  return false;
}

export function shouldReuseBackend(env = process.env) {
  const value = String(env.DATAVERSE_REUSE_BACKEND || '').toLowerCase();
  return value === '1' || value === 'true';
}

async function main() {
  const plan = createDevPlan();
  const env = {
    ...process.env,
    NEXT_PUBLIC_DATAVERSE_API_URL: plan.apiUrl,
  };

  console.log(`[dev] Frontend API URL: ${plan.apiUrl}`);

  let backendProcess;
  let backendAlreadyRunning = await isPortOpen(plan.backendTarget.host, plan.backendTarget.port);
  
  if (backendAlreadyRunning && !shouldReuseBackend(process.env)) {
    console.log(`[dev] Port ${plan.backendTarget.port} is already in use. Terminating existing process to connect fresh backend...`);
    const killed = killPort(plan.backendTarget.port);
    if (killed) {
      // Wait for port release
      await new Promise((resolve) => setTimeout(resolve, 1500));
      backendAlreadyRunning = await isPortOpen(plan.backendTarget.host, plan.backendTarget.port);
    }
  }

  if (backendAlreadyRunning) {
    console.log(`[dev] Reusing existing backend on ${plan.apiUrl}`);
    const backendHealthy = await waitForBackendHealth(plan.apiUrl, 10_000);
    if (!backendHealthy) {
      console.error(`[dev] Port ${plan.backendTarget.port} is open, but ${plan.healthUrl} is not healthy.`);
      console.error('[dev] Stop the process on that port or run without DATAVERSE_REUSE_BACKEND so the launcher can start DataVerse backend.');
      process.exit(1);
    }
  } else {
    console.log('[dev] Starting FastAPI backend on http://127.0.0.1:8000');
    backendProcess = startProcess('backend', plan.backend, env);

    const backendReady = await waitForBackendHealth(plan.apiUrl, STARTUP_TIMEOUT_MS);

    if (!backendReady) {
      console.error(`[dev] Backend did not pass health check at ${plan.healthUrl} within 120 seconds.`);
      if (backendProcess) {
        backendProcess.kill('SIGTERM');
      }
      process.exit(1);
    }
  }

  const frontendHost = process.env.NEXT_FRONTEND_HOST || '127.0.0.1';
  const frontendPort = Number(process.env.NEXT_FRONTEND_PORT || '3000');
  let frontendAlreadyRunning = await isPortOpen(frontendHost, frontendPort);
  if (frontendAlreadyRunning) {
    console.log(`[dev] Port ${frontendPort} is already in use. Terminating existing process...`);
    const killed = killPort(frontendPort);
    if (killed) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }

  console.log(`[dev] Starting Next.js frontend on http://${frontendHost}:${frontendPort}`);
  const frontendProcess = startProcess('frontend', plan.frontend, env);

  const shutdown = (signal) => {
    frontendProcess.kill(signal);
    if (backendProcess) {
      backendProcess.kill(signal);
    }
  };

  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);

  frontendProcess.once('exit', (code) => {
    if (backendProcess) {
      backendProcess.kill('SIGTERM');
    }
    process.exit(code ?? 0);
  });
}

if (isMainModule(import.meta.url, process.argv[1])) {
  main().catch((error) => {
    console.error('[dev] Failed to start full stack dev environment');
    console.error(error);
    process.exit(1);
  });
}
