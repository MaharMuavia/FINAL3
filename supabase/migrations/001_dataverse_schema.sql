-- DataVerse AI chat/session persistence schema.
-- Backend uses SUPABASE_SERVICE_ROLE_KEY for server-only access. Do not expose
-- service-role credentials to the frontend.

create extension if not exists pgcrypto;

create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid null,
  title text not null default 'New Chat',
  status text not null default 'active',
  active_dataset_id uuid null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_message_at timestamptz null
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system', 'agent')),
  content text not null,
  message_type text not null default 'text',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.datasets (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  user_id uuid null,
  filename text not null,
  original_filename text null,
  storage_path text not null,
  file_type text not null,
  file_size bigint not null default 0,
  row_count integer not null default 0,
  column_count integer not null default 0,
  columns jsonb not null default '[]'::jsonb,
  schema_profile jsonb not null default '{}'::jsonb,
  semantic_map jsonb not null default '{}'::jsonb,
  status text not null default 'uploaded',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  dataset_id uuid null references public.datasets(id) on delete set null,
  agent_name text not null,
  status text not null,
  input jsonb not null default '{}'::jsonb,
  output jsonb not null default '{}'::jsonb,
  error text null,
  started_at timestamptz not null default now(),
  completed_at timestamptz null
);

create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  dataset_id uuid null references public.datasets(id) on delete set null,
  title text not null,
  report_type text not null default 'analysis',
  format text not null default 'html,pdf',
  storage_path text not null,
  public_url text null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_chat_sessions_updated_at on public.chat_sessions(updated_at desc);
create index if not exists idx_chat_messages_session_id on public.chat_messages(session_id, created_at);
create index if not exists idx_datasets_session_id on public.datasets(session_id, created_at desc);
create index if not exists idx_agent_runs_session_id on public.agent_runs(session_id, started_at);
create index if not exists idx_reports_session_id on public.reports(session_id, created_at desc);

insert into storage.buckets (id, name, public)
values
  ('dataverse-datasets', 'dataverse-datasets', false),
  ('dataverse-reports', 'dataverse-reports', false)
on conflict (id) do nothing;

alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;
alter table public.datasets enable row level security;
alter table public.agent_runs enable row level security;
alter table public.reports enable row level security;

-- RLS policy design note:
-- The current backend is service-role only, so the service role bypasses RLS.
-- Add user-scoped policies before exposing these tables directly to browsers.
