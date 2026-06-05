import {
  API_BASE_URL,
  uploadDataset,
  askDataset,
  getProfile,
  deleteDataset,
  type UploadResponse,
  type AskResponse,
  type ProfileResponse,
} from './dataverse-api';

async function contract(file: File): Promise<void> {
  const uploaded: UploadResponse = await uploadDataset(file);
  const answer: AskResponse = await askDataset(uploaded.dataset_id, 'summarize');
  const profile: ProfileResponse = await getProfile(uploaded.dataset_id);
  await deleteDataset(uploaded.dataset_id);

  API_BASE_URL.toString();
  uploaded.column_names.map((col) => col.toLowerCase());
  answer.tables.map((t) => t.title);
  profile.columns.length;
}

void contract;
