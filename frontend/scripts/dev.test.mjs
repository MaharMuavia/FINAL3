import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { createDevPlan, isMainModule, shouldReuseBackend, waitForBackendHealth } from './dev.mjs';

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(frontendDir, '..');

test('createDevPlan wires frontend dev to the local backend by default', () => {
  const plan = createDevPlan({
    frontendDir,
    env: {},
    platform: 'win32',
    nodePath: 'node.exe',
  });

  assert.equal(plan.apiUrl, 'http://localhost:8000/api');
  assert.equal(plan.apiOrigin, 'http://localhost:8000');
  assert.equal(plan.healthUrl, 'http://localhost:8000/health/live');
  assert.equal(plan.backend.cwd, repoRoot);
  assert.match(plan.backend.command, /python\.exe$/);
  assert.deepEqual(plan.backend.args, [
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
  ]);
  assert.equal(plan.frontend.command, 'node.exe');
  assert.equal(plan.frontend.args.at(-4), '--hostname');
  assert.equal(plan.frontend.args.at(-3), '127.0.0.1');
  assert.equal(plan.frontend.args.at(-2), '--port');
  assert.equal(plan.frontend.args.at(-1), '3000');
});

test('createDevPlan preserves an explicit backend URL', () => {
  const plan = createDevPlan({
    frontendDir,
    env: { NEXT_PUBLIC_DATAVERSE_API_URL: 'http://localhost:9000/' },
    platform: 'linux',
    nodePath: '/usr/bin/node',
  });

  assert.equal(plan.apiUrl, 'http://localhost:9000');
  assert.equal(plan.apiOrigin, 'http://localhost:9000');
});

test('createDevPlan accepts an explicit /api backend URL', () => {
  const plan = createDevPlan({
    frontendDir,
    env: { NEXT_PUBLIC_DATAVERSE_API_URL: 'http://localhost:9000/api/' },
    platform: 'linux',
    nodePath: '/usr/bin/node',
  });

  assert.equal(plan.apiUrl, 'http://localhost:9000/api');
  assert.equal(plan.apiOrigin, 'http://localhost:9000');
  assert.equal(plan.healthUrl, 'http://localhost:9000/health/live');
});

test('isMainModule recognizes Windows script paths', () => {
  const scriptPath = path.join(frontendDir, 'scripts', 'dev.mjs');
  const moduleUrl = new URL(`file:///${scriptPath.replace(/\\/g, '/')}`).href;

  assert.equal(isMainModule(moduleUrl, scriptPath), true);
});

test('shouldReuseBackend requires explicit opt in', () => {
  assert.equal(shouldReuseBackend({}), false);
  assert.equal(shouldReuseBackend({ DATAVERSE_REUSE_BACKEND: '1' }), true);
  assert.equal(shouldReuseBackend({ DATAVERSE_REUSE_BACKEND: 'true' }), true);
});

test('waitForBackendHealth checks the backend liveness endpoint', async () => {
  const requestedUrls = [];
  const healthy = await waitForBackendHealth('http://localhost:8000/api', 1000, async (url) => {
    requestedUrls.push(url);
    return { ok: true };
  });

  assert.equal(healthy, true);
  assert.deepEqual(requestedUrls, ['http://localhost:8000/health/live']);
});
