import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import path from 'node:path';
import * as ts from 'typescript';
import { fileURLToPath } from 'node:url';

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const apiConfigPath = path.join(frontendDir, 'lib', 'apiConfig.ts');
const apiClientPath = path.join(frontendDir, 'lib', 'dataverse-api.ts');
const appPath = path.join(frontendDir, 'app', 'page.tsx');

async function loadApiConfig(env = {}) {
  const previousDataverse = process.env.NEXT_PUBLIC_DATAVERSE_API_URL;
  const previousApi = process.env.NEXT_PUBLIC_API_URL;
  process.env.NEXT_PUBLIC_DATAVERSE_API_URL = env.NEXT_PUBLIC_DATAVERSE_API_URL ?? '';
  process.env.NEXT_PUBLIC_API_URL = env.NEXT_PUBLIC_API_URL ?? '';

  const source = readFileSync(apiConfigPath, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const imported = await import(`data:text/javascript,${encodeURIComponent(output)}#${Math.random()}`);

  if (previousDataverse === undefined) {
    delete process.env.NEXT_PUBLIC_DATAVERSE_API_URL;
  } else {
    process.env.NEXT_PUBLIC_DATAVERSE_API_URL = previousDataverse;
  }
  if (previousApi === undefined) {
    delete process.env.NEXT_PUBLIC_API_URL;
  } else {
    process.env.NEXT_PUBLIC_API_URL = previousApi;
  }

  return imported;
}

test('API base URL normalizes env values with /api', async () => {
  const config = await loadApiConfig({ NEXT_PUBLIC_DATAVERSE_API_URL: 'http://localhost:8000/api/' });

  assert.equal(config.API_BASE_URL, 'http://localhost:8000/api');
  assert.equal(config.API_HEALTH_URL, 'http://localhost:8000/health/live');
});

test('API base URL appends /api when env omits it', async () => {
  const config = await loadApiConfig({ NEXT_PUBLIC_API_URL: 'http://localhost:8000' });

  assert.equal(config.API_BASE_URL, 'http://localhost:8000/api');
  assert.equal(config.API_HEALTH_URL, 'http://localhost:8000/health/live');
});

test('frontend app and API client do not hardcode legacy local backend URLs', () => {
  const forbidden = ['http://127.0.0.1:8000', 'http://localhost:8000/api/upload'];
  const checkedFiles = [apiClientPath, appPath];

  for (const file of checkedFiles) {
    const source = readFileSync(file, 'utf8');
    for (const value of forbidden) {
      assert.equal(source.includes(value), false, `${path.relative(frontendDir, file)} contains ${value}`);
    }
  }
});

test('upload and chat use session-based backend routes', () => {
  const source = readFileSync(apiClientPath, 'utf8');

  assert.match(source, /buildApiUrl\(`\/sessions\/\$\{targetSessionId\}\/datasets\/upload\?\$\{params\}`\)/);
  assert.match(source, /buildApiUrl\(`\/sessions\/\$\{sessionId\}\/messages`\)/);
  assert.match(source, /JSON\.stringify\(\{ content: query, dataset_id: datasetId \}\)/);
  assert.doesNotMatch(source, /\/api\/upload|\/api\/query/);
});

test('backend unavailable error includes URL, command, and env variable help', () => {
  const source = readFileSync(apiClientPath, 'utf8');

  assert.match(source, /Backend is not running/);
  assert.match(source, /NEXT_PUBLIC_DATAVERSE_API_URL/);
  assert.match(source, /BACKEND_START_COMMAND/);
  assert.match(source, /API_BASE_URL/);
});
