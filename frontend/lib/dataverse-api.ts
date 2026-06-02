export const API_BASE_URL =
  process.env.NEXT_PUBLIC_DATAVERSE_API_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8000';

export type UploadResponse = {
  session_id: string;
  success: boolean;
  message: string;
  is_retail: boolean;
  matched_keywords?: string[];
  dataset_filename?: string;
  dataset_rows?: number;
  dataset_cols?: number;
  dataset_id?: string;
  column_names?: string[];
  column_dtypes?: string[];
  dataset_preview?: Array<Record<string, unknown>>;
  dataset_type?: string;
  column_roles?: Record<string, string>;
  dataset_profile?: {
    row_count?: number;
    column_count?: number;
    semantic_columns?: Record<string, string | null>;
    column_roles?: Record<string, string>;
    dataset_type?: string;
    missing_values?: Record<string, { count: number; pct: number }>;
    numeric_summary?: Record<string, Record<string, number | null>>;
    quality?: {
      score?: number;
      duplicate_rows?: number;
      total_missing?: number;
      total_cells?: number;
    };
    [key: string]: unknown;
  };
  created_at?: string;
};

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
  rows: Array<Record<string, unknown>>;
};

export type ChatEvent = {
  step: string;
  message: string;
  chart?: ChartPayload;
  chart_spec?: {
    data?: Array<Record<string, unknown>>;
    layout?: Record<string, unknown>;
  };
  table?: TablePayload;
  warnings?: string[];
  recommendations?: string[];
  suggestions?: string[];
  [key: string]: unknown;
};

export class DataVerseApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
    this.name = 'DataVerseApiError';
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') {
      return body.detail;
    }
    return JSON.stringify(body);
  } catch {
    return response.statusText || 'Request failed';
  }
}

export async function uploadDataset(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);

  const response = await fetch(`${API_BASE_URL}/api/upload`, {
    method: 'POST',
    body: form,
  });

  if (!response.ok) {
    throw new DataVerseApiError(await readError(response), response.status);
  }

  return response.json() as Promise<UploadResponse>;
}

export async function streamQuery(
  sessionId: string,
  query: string,
  onEvent?: (event: ChatEvent) => void,
): Promise<ChatEvent[]> {
  const url = new URL(`${API_BASE_URL}/api/stream/query`);
  url.searchParams.set('session_id', sessionId);
  url.searchParams.set('query', query);

  const response = await fetch(url);
  if (!response.ok || !response.body) {
    throw new DataVerseApiError(await readError(response), response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const events: ChatEvent[] = [];
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';

    for (const chunk of chunks) {
      const dataLine = chunk
        .split('\n')
        .find((line) => line.startsWith('data:'));

      if (!dataLine) {
        continue;
      }

      const event = JSON.parse(dataLine.slice(5).trim()) as ChatEvent;
      events.push(event);
      onEvent?.(event);
    }
  }

  return events;
}
