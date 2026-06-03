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

export type AskResponse = {
  answer: string;
  summary: string;
  tables: TablePayload[];
  charts: ChartPayload[];
  recommendations: string[];
  warnings: string[];
  next_questions: string[];
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

export class DataVerseApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'DataVerseApiError';
    this.status = status;
  }
}

// ── API Functions ──────────────────────────────────────

export async function uploadDataset(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);

  const resp = await fetch(`${API_BASE_URL}/api/datasets/upload`, {
    method: 'POST',
    body: form,
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: 'Upload failed' }));
    throw new DataVerseApiError(body.detail || 'Upload failed', resp.status);
  }

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
}
