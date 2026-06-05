/**
 * DataVerse AI API client for the session-based backend.
 */

import {
  API_BASE_URL,
  API_FALLBACK_HEALTH_URL,
  API_HEALTH_URL,
  BACKEND_ENV_HELP,
  BACKEND_START_COMMAND,
  buildApiUrl,
} from './apiConfig';

export { API_BASE_URL, API_HEALTH_URL, BACKEND_START_COMMAND } from './apiConfig';

const WORKSPACE_USER_ID_KEY = 'dataverse.workspaceUserId';
const USER_HEADER = 'X-Dataverse-User';

function createWorkspaceUserId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (value) => (
    (Number(value) ^ Math.random() * 16 >> Number(value) / 4).toString(16)
  ));
}

function getWorkspaceUserId() {
  if (typeof window === 'undefined') {
    return null;
  }

  const existing = window.localStorage.getItem(WORKSPACE_USER_ID_KEY);
  if (existing) {
    return existing;
  }

  const next = createWorkspaceUserId();
  window.localStorage.setItem(WORKSPACE_USER_ID_KEY, next);
  return next;
}

function withWorkspaceHeaders(init?: RequestInit): RequestInit {
  const userId = getWorkspaceUserId();
  if (!userId) {
    return init ?? {};
  }

  const headers = new Headers(init?.headers);
  headers.set(USER_HEADER, userId);
  return { ...init, headers };
}

export type ChartPayload = {
  type: 'bar' | 'line' | 'pie' | 'donut' | string;
  title: string;
  data: Array<Record<string, unknown>>;
  x_key: string;
  y_key?: string;
  series_key?: string;
};

export type TablePayload = {
  title: string;
  columns: string[];
  rows: Record<string, unknown>[];
};

export type AgentStep = {
  name: string;
  status: string;
  timestamp?: string;
  message?: string;
};

export type AgentSummary = {
  name: string;
  status: string;
  summary?: string;
  steps?: AgentStep[];
};

export type AnalysisResponse = {
  session_id: string;
  dataset_id: string;
  title: string;
  agents: AgentSummary[];
  answer: string;
  tables?: TablePayload[];
  charts?: ChartPayload[];
  warnings?: string[];
  recommendations?: string[];
  report?: {
    report_id: string;
    html_url?: string;
    pdf_url?: string;
  } | null;
};

export type UploadResponse = {
  session_id: string;
  success: boolean;
  is_retail: boolean;
  message: string;
  dataset_id: string;
  dataset_filename: string;
  dataset_rows?: number;
  dataset_cols?: number;
  column_names: string[];
  column_dtypes: string[];
  dataset_profile: Record<string, unknown>;
  dataset_preview?: Array<Record<string, unknown>>;
  dataset_type?: string;
  created_at?: string;
  analysis?: AnalysisResponse | null;
};

export type AskResponse = {
  answer: string;
  summary: string;
  tables: TablePayload[];
  charts: ChartPayload[];
  recommendations: string[];
  warnings: string[];
  next_questions: string[];
};

export type ChatSessionSummary = {
  id: string;
  title: string;
  active_dataset_id?: string | null;
  updated_at?: string;
  message_count?: number;
};

export type RecentDataset = {
  id: string;
  session_id: string;
  filename: string;
  original_filename?: string;
  row_count?: number;
  column_count?: number;
  columns?: Array<{ name?: string; dtype?: string } | string>;
  schema_profile?: Record<string, unknown>;
  semantic_map?: Record<string, unknown>;
  created_at?: string;
  dataset?: UploadResponse;
};

export type SessionDetail = ChatSessionSummary & {
  messages: Array<{
    id: string;
    role: 'user' | 'assistant' | 'system' | 'agent';
    content: string;
    message_type?: string;
    payload?: Record<string, unknown>;
    created_at?: string;
  }>;
  datasets: RecentDataset[];
  agent_runs: Array<Record<string, unknown>>;
  reports: Array<Record<string, unknown>>;
};

export type ProfileResponse = {
  dataset_id: string;
  row_count: number;
  column_count: number;
  columns: string[];
  profile: Record<string, unknown>;
};

export type ChatEvent = {
  step: string;
  message: string;
  table?: TablePayload;
  chart?: ChartPayload;
  recommendations?: string[];
  suggestions?: string[];
};

export class DataVerseApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'DataVerseApiError';
    this.status = status;
  }
}

export type BackendHealth = {
  connected: boolean;
  url: string;
  detail?: string;
};

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body.detail || body.message || response.statusText || 'Unknown error';
  } catch {
    try {
      return (await response.text()) || response.statusText || 'Unknown error';
    } catch {
      return response.statusText || 'Unknown error';
    }
  }
}

async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, withWorkspaceHeaders(init));
  } catch (error) {
    if (error instanceof DataVerseApiError) {
      throw error;
    }
    const detail = error instanceof Error ? error.message : 'Network request failed';
    throw new DataVerseApiError(
      [
        `Backend is not running or not reachable at ${API_BASE_URL}.`,
        `Start FastAPI on port 8000 with: ${BACKEND_START_COMMAND}`,
        `${BACKEND_ENV_HELP}`,
        `Network detail: ${detail}`,
      ].join(' '),
      0,
    );
  }
}

export async function checkBackendHealth(): Promise<BackendHealth> {
  for (const url of [API_HEALTH_URL, API_FALLBACK_HEALTH_URL]) {
    try {
      const response = await fetch(url, withWorkspaceHeaders({ cache: 'no-store' }));
      if (response.ok) {
        return { connected: true, url };
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Network request failed';
      return { connected: false, url, detail };
    }
  }
  return { connected: false, url: API_HEALTH_URL, detail: 'Health check returned a non-OK response.' };
}

export async function ensureBackendAvailable(): Promise<void> {
  const health = await checkBackendHealth();
  if (!health.connected) {
    throw new DataVerseApiError(
      [
        `Backend is not running. Start FastAPI on port 8000 or update NEXT_PUBLIC_DATAVERSE_API_URL.`,
        `Using API URL: ${API_BASE_URL}.`,
        `Health check: ${health.url}.`,
        `Command: ${BACKEND_START_COMMAND}`,
        health.detail ? `Detail: ${health.detail}` : '',
      ].filter(Boolean).join(' '),
      0,
    );
  }
}

export async function createSession(title = 'New Chat'): Promise<ChatSessionSummary> {
  const response = await apiFetch(buildApiUrl('/sessions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  const data = await response.json();
  return { id: data.session_id || data.id, title: data.title, updated_at: data.created_at };
}

export async function listSessions(): Promise<ChatSessionSummary[]> {
  const response = await apiFetch(buildApiUrl('/sessions'));
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  return response.json() as Promise<ChatSessionSummary[]>;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const response = await apiFetch(buildApiUrl(`/sessions/${sessionId}`));
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  return response.json() as Promise<SessionDetail>;
}

export async function listDatasets(): Promise<RecentDataset[]> {
  const response = await apiFetch(buildApiUrl('/datasets'));
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  return response.json() as Promise<RecentDataset[]>;
}

export async function uploadDataset(
  file: File,
  sessionId?: string,
  options: { autoAnalyze?: boolean; generateReport?: boolean; runXai?: boolean } = {},
): Promise<UploadResponse> {
  await ensureBackendAvailable();
  const targetSessionId = sessionId || (await createSession()).id;
  const form = new FormData();
  form.append('file', file);

  const params = new URLSearchParams({
    auto_analyze: String(options.autoAnalyze ?? true),
    generate_report: String(options.generateReport ?? false),
    run_xai: String(options.runXai ?? false),
  });

  const response = await apiFetch(buildApiUrl(`/sessions/${targetSessionId}/datasets/upload?${params}`), {
    method: 'POST',
    body: form,
  });

  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }

  const payload = await response.json();
  const dataset = payload.dataset ?? {};
  const columns = payload.columns ?? dataset.columns ?? [];
  const schemaProfile = dataset.schema_profile as ({ dataset_type?: string; semantic_map?: { dataset_type?: string }; preview?: Array<Record<string, unknown>> } | undefined);
  const semanticMap = dataset.semantic_map as ({ dataset_type?: string } | undefined);
  return {
    session_id: payload.session_id,
    success: true,
    message: payload.analysis ? 'Dataset uploaded and analyzed.' : 'Dataset uploaded.',
    is_retail: false,
    dataset_id: payload.dataset_id,
    dataset_filename: payload.filename,
    dataset_rows: payload.row_count,
    dataset_cols: payload.column_count,
    column_names: columns.map((column: { name?: string } | string) => typeof column === 'string' ? column : column.name || ''),
    column_dtypes: columns.map((column: { dtype?: string } | string) => typeof column === 'string' ? '' : column.dtype || ''),
    dataset_profile: schemaProfile ?? {},
    dataset_preview: schemaProfile?.preview,
    dataset_type: semanticMap?.dataset_type ?? schemaProfile?.semantic_map?.dataset_type ?? schemaProfile?.dataset_type,
    created_at: dataset.created_at,
    analysis: payload.analysis ?? null,
  };
}

export async function askDataset(datasetId: string, prompt: string): Promise<AskResponse> {
  await ensureBackendAvailable();
  const response = await apiFetch(buildApiUrl(`/datasets/${datasetId}/ask`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });

  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }

  return response.json();
}

export async function getProfile(datasetId: string): Promise<ProfileResponse> {
  const response = await apiFetch(buildApiUrl(`/datasets/${datasetId}/profile`));

  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }

  return response.json();
}

export async function deleteDataset(datasetId: string): Promise<{ dataset_id: string; deleted: boolean }> {
  const response = await apiFetch(buildApiUrl(`/datasets/${datasetId}`), {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }

  return response.json();
}

export async function analyzeSession(
  sessionId: string,
  datasetId: string,
  userPrompt = 'Analyze this dataset',
): Promise<AnalysisResponse> {
  await ensureBackendAvailable();
  const response = await apiFetch(buildApiUrl(`/sessions/${sessionId}/analyze`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, user_prompt: userPrompt, run_xai: true, generate_report: true }),
  });
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  return response.json() as Promise<AnalysisResponse>;
}

export async function streamQuery(
  sessionId: string,
  query: string,
  datasetId?: string,
  onEvent?: (event: ChatEvent) => void,
): Promise<ChatEvent[]> {
  await ensureBackendAvailable();
  const response = await apiFetch(buildApiUrl(`/sessions/${sessionId}/messages`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: query, dataset_id: datasetId }),
  });
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  const result = await response.json() as AnalysisResponse;
  const events: ChatEvent[] = [
    ...(result.agents ?? []).flatMap((agent) => {
      const steps = agent.steps?.map((step) => ({
        step: agent.name,
        message: `${agent.name} / ${step.name}: ${step.status}`,
      })) ?? [];
      return [
        { step: agent.name, message: `${agent.name}: ${agent.status}${agent.summary ? ` - ${agent.summary}` : ''}` },
        ...steps,
      ];
    }),
    ...(result.charts ?? []).map((chart) => ({
      step: 'chart',
      message: `Chart ready: ${chart.title}`,
      chart,
    })),
    ...(result.tables ?? []).map((table) => ({
      step: 'table',
      message: `Table ready: ${table.title}`,
      table,
    })),
    { step: 'narration', message: result.answer, recommendations: result.recommendations },
  ];
  events.forEach((event) => onEvent?.(event));

  return events;
}
