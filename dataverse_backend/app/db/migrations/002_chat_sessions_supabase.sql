-- ChatGPT-style DataVerse AI persistence schema for Supabase/Postgres.
-- Tables are intended to be accessed from the backend with the Supabase service role key only.

create extension if not exists "pgcrypto";

create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id text null,
  title text not null default 'New Chat',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_message_at timestamptz null,
  active_dataset_id uuid null,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  role text not null check (role in ('user','assistant','system','agent')),
  content text not null default '',
  message_type text not null default 'text',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.datasets (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  user_id text null,
  filename text not null,
  original_filename text not null,
  storage_path text not null,
  file_type text null,
  file_size bigint null,
  row_count int null,
  column_count int null,
  columns jsonb not null default '[]'::jsonb,
  schema_profile jsonb not null default '{}'::jsonb,
  semantic_map jsonb not null default '{}'::jsonb,
  status text not null default 'uploaded',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.chat_sessions
  add constraint chat_sessions_active_dataset_fk
  foreign key (active_dataset_id) references public.datasets(id) on delete set null;

create table if not exists public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  agent_name text not null,
  status text not null default 'pending',
  input jsonb not null default '{}'::jsonb,
  output jsonb not null default '{}'::jsonb,
  error text null,
  started_at timestamptz not null default now(),
  completed_at timestamptz null
);

create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  title text null,
  report_type text not null default 'analysis',
  format text null,
  storage_path text null,
  public_url text null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists chat_sessions_updated_at_idx on public.chat_sessions(updated_at desc);
create index if not exists chat_messages_session_created_idx on public.chat_messages(session_id, created_at);
create index if not exists datasets_session_created_idx on public.datasets(session_id, created_at desc);
create index if not exists datasets_created_at_idx on public.datasets(created_at desc);
create index if not exists agent_runs_session_started_idx on public.agent_runs(session_id, started_at);
create index if not exists reports_session_created_idx on public.reports(session_id, created_at desc);

alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;
alter table public.datasets enable row level security;
alter table public.agent_runs enable row level security;
alter table public.reports enable row level security;

-- Future auth-ready policies. The backend service role bypasses RLS.
drop policy if exists "Users can read own chat sessions" on public.chat_sessions;
create policy "Users can read own chat sessions"
  on public.chat_sessions for select
  using (user_id is null or user_id = auth.uid()::text);

drop policy if exists "Users can read own chat messages" on public.chat_messages;
create policy "Users can read own chat messages"
  on public.chat_messages for select
  using (
    exists (
      select 1 from public.chat_sessions s
      where s.id = chat_messages.session_id
        and (s.user_id is null or s.user_id = auth.uid()::text)
    )
  );

drop policy if exists "Users can read own datasets" on public.datasets;
create policy "Users can read own datasets"
  on public.datasets for select
  using (user_id is null or user_id = auth.uid()::text);

drop policy if exists "Users can read own agent runs" on public.agent_runs;
create policy "Users can read own agent runs"
  on public.agent_runs for select
  using (
    exists (
      select 1 from public.chat_sessions s
      where s.id = agent_runs.session_id
        and (s.user_id is null or s.user_id = auth.uid()::text)
    )
  );

drop policy if exists "Users can read own reports" on public.reports;
create policy "Users can read own reports"
  on public.reports for select
  using (
    exists (
      select 1 from public.chat_sessions s
      where s.id = reports.session_id
        and (s.user_id is null or s.user_id = auth.uid()::text)
    )
  );

insert into storage.buckets (id, name, public)
values ('dataverse-datasets', 'dataverse-datasets', false)
on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
values ('dataverse-reports', 'dataverse-reports', false)
on conflict (id) do nothing;
