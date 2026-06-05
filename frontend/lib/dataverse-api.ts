/**
 * DataVerse AI API client for the session-based backend.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_DATAVERSE_API_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8000';

export type ChartPayload = {
  type: 'bar' | 'line' | 'pie' | 'donut' | string;
  title: string;
  data: Array<Record<string, unknown>>;
  x_key: string;
  y_key?: string;
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

export async function uploadDataset(
  file: File,
  sessionId?: string,
  options: { autoAnalyze?: boolean; generateReport?: boolean; runXai?: boolean } = {},
): Promise<UploadResponse> {
  const targetSessionId = sessionId || (await createSession()).id;
  const form = new FormData();
  form.append('file', file);

  const params = new URLSearchParams({
    auto_analyze: String(options.autoAnalyze ?? false),
    generate_report: String(options.generateReport ?? true),
    run_xai: String(options.runXai ?? true),
  });

  const response = await fetch(`${API_BASE_URL}/api/sessions/${targetSessionId}/datasets/upload?${params}`, {
    method: 'POST',
    body: form,
  });

  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }

  const payload = await response.json();
  const dataset = payload.dataset ?? {};
  const columns = payload.columns ?? dataset.columns ?? [];
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
    dataset_profile: dataset.schema_profile ?? {},
    dataset_preview: dataset.schema_profile?.preview,
    dataset_type: dataset.schema_profile?.dataset_type,
    created_at: dataset.created_at,
    analysis: payload.analysis ?? null,
  };
}

export async function askDataset(datasetId: string, prompt: string): Promise<AskResponse> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}/ask`, {
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
  const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}/profile`);

  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }

  return response.json();
}

export async function deleteDataset(datasetId: string): Promise<{ dataset_id: string; deleted: boolean }> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}`, {
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
    { step: 'narration', message: result.answer, recommendations: result.recommendations },
  ];
  events.forEach((event) => onEvent?.(event));

  return events;
}
