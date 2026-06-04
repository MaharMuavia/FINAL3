/**
 * DataVerse AI API client — clean interface for 4 endpoints.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_DATAVERSE_API_URL || 'http://127.0.0.1:8000';

// ── Types ──────────────────────────────────────────────

export type UploadResponse = {
  dataset_id: string;
  filename: string;
  row_count: number;
  column_count: number;
  columns: string[];
  profile: Record<string, unknown>;
  message: string;
};

<<<<<<< HEAD
export type AskResponse = {
  answer: string;
  summary: string;
  tables: TablePayload[];
  charts: ChartPayload[];
  recommendations: string[];
  warnings: string[];
  next_questions: string[];
=======
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

export type ChartPayload = {
  type: 'bar' | 'line' | 'pie' | 'donut' | string;
  title: string;
  data: Array<Record<string, unknown>>;
  x_key: string;
  y_key?: string;
>>>>>>> 15b8a6d8 (new1)
};

export type TablePayload = {
  title: string;
  columns: string[];
  rows: Record<string, unknown>[];
};

export type ChartPayload = {
  title: string;
  type: 'bar' | 'line' | 'pie';
  x_key: string;
  y_key: string;
  data: Record<string, unknown>[];
};

export type ProfileResponse = {
  dataset_id: string;
  row_count: number;
  column_count: number;
  columns: string[];
  profile: Record<string, unknown>;
};

export type AnalysisResponse = {
  session_id: string;
  dataset_id: string;
  title: string;
  agents: Array<{ name: string; status: string; summary?: string }>;
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

export class DataVerseApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'DataVerseApiError';
    this.status = status;
  }
}

// ── API Functions ──────────────────────────────────────

export async function createSession(title = 'New Chat'): Promise<ChatSessionSummary> {
  const response = await fetch(`${API_BASE_URL}/api/sessions`, {
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
  const response = await fetch(`${API_BASE_URL}/api/sessions`);
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  return response.json() as Promise<ChatSessionSummary[]>;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`);
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  return response.json() as Promise<SessionDetail>;
}

export async function listDatasets(): Promise<RecentDataset[]> {
  const response = await fetch(`${API_BASE_URL}/api/datasets`);
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  return response.json() as Promise<RecentDataset[]>;
}

export async function uploadDataset(file: File, sessionId?: string): Promise<UploadResponse> {
  const targetSessionId = sessionId || (await createSession()).id;
  const form = new FormData();
  form.append('file', file);

<<<<<<< HEAD
  const resp = await fetch(`${API_BASE_URL}/api/datasets/upload`, {
=======
  const response = await fetch(`${API_BASE_URL}/api/sessions/${targetSessionId}/datasets/upload`, {
>>>>>>> 15b8a6d8 (new1)
    method: 'POST',
    body: form,
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: 'Upload failed' }));
    throw new DataVerseApiError(body.detail || 'Upload failed', resp.status);
  }

<<<<<<< HEAD
  return resp.json();
}

export async function askDataset(
  datasetId: string,
  prompt: string,
): Promise<AskResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: 'Query failed' }));
    throw new DataVerseApiError(body.detail || 'Query failed', resp.status);
  }

  return resp.json();
}

export async function getProfile(
  datasetId: string,
): Promise<ProfileResponse> {
  const resp = await fetch(
    `${API_BASE_URL}/api/datasets/${datasetId}/profile`,
  );

  if (!resp.ok) {
    const body = await resp
      .json()
      .catch(() => ({ detail: 'Failed to get profile' }));
    throw new DataVerseApiError(
      body.detail || 'Failed to get profile',
      resp.status,
    );
  }

  return resp.json();
}

export async function deleteDataset(
  datasetId: string,
): Promise<{ dataset_id: string; deleted: boolean }> {
  const resp = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}`, {
    method: 'DELETE',
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: 'Delete failed' }));
    throw new DataVerseApiError(body.detail || 'Delete failed', resp.status);
  }

  return resp.json();
=======
  const payload = await response.json();
  const dataset = payload.dataset ?? {};
  return {
    session_id: payload.session_id,
    success: true,
    message: 'Dataset uploaded.',
    is_retail: false,
    dataset_id: payload.dataset_id,
    dataset_filename: payload.filename,
    dataset_rows: payload.row_count,
    dataset_cols: payload.column_count,
    column_names: (payload.columns ?? []).map((column: { name?: string } | string) => typeof column === 'string' ? column : column.name || ''),
    column_dtypes: (payload.columns ?? []).map((column: { dtype?: string } | string) => typeof column === 'string' ? '' : column.dtype || ''),
    dataset_profile: dataset.schema_profile,
    dataset_type: dataset.schema_profile?.dataset_type,
    created_at: dataset.created_at,
  };
}

export async function analyzeSession(sessionId: string, datasetId: string, userPrompt = 'Analyze this dataset'): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/analyze`, {
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
  onEvent?: (event: ChatEvent) => void,
): Promise<ChatEvent[]> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: query }),
  });
  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }
  const result = await response.json() as AnalysisResponse;
  const events: ChatEvent[] = [
    ...(result.agents ?? []).map((agent) => ({ step: agent.name, message: `${agent.name}: ${agent.status}${agent.summary ? ` - ${agent.summary}` : ''}` })),
    { step: 'narration', message: result.answer, recommendations: result.recommendations },
  ];
  events.forEach((event) => onEvent?.(event));

  return events;
>>>>>>> 15b8a6d8 (new1)
}
