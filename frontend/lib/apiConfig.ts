const DEFAULT_BACKEND_URL = 'http://localhost:8000/api';

function trimTrailingSlashes(value: string) {
  return value.replace(/\/+$/, '');
}

export function normalizeApiBaseUrl(value?: string | null) {
  const raw = trimTrailingSlashes(value?.trim() || DEFAULT_BACKEND_URL);
  return raw.endsWith('/api') ? raw : `${raw}/api`;
}

export const API_BASE_URL = normalizeApiBaseUrl(
  process.env.NEXT_PUBLIC_DATAVERSE_API_URL || process.env.NEXT_PUBLIC_API_URL,
);

export const API_ORIGIN_URL = API_BASE_URL.endsWith('/api')
  ? API_BASE_URL.slice(0, -4)
  : API_BASE_URL;

export const API_HEALTH_URL = `${API_ORIGIN_URL}/health/live`;
export const API_FALLBACK_HEALTH_URL = `${API_BASE_URL}/health`;

export const BACKEND_START_COMMAND =
  'cd dataverse_backend; python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000';

export const BACKEND_ENV_HELP =
  'Set NEXT_PUBLIC_DATAVERSE_API_URL or NEXT_PUBLIC_API_URL to your FastAPI URL, for example http://localhost:8000/api.';

export function buildApiUrl(path: string) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}
