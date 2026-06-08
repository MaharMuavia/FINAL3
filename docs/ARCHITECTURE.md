# DataVerse AI Architecture

## Current Architecture

DataVerse AI is a full-stack dataset analysis application with one active user flow:

1. A user opens the Next.js frontend.
2. The frontend creates a chat session through FastAPI.
3. The user uploads a CSV or Excel file.
4. The backend parses the file, profiles it, infers semantic meaning, computes analytics, optionally trains an ML model, optionally runs XAI, and can generate a report.
5. The frontend renders the answer as chat text, tables, KPI cards, charts, and report download links.

The system is deterministic first. LLMs help with semantic refinement, query planning, titles, and narration, but numeric results come from pandas and scikit-learn code in the backend.

## Text Diagram

```text
Browser / Next.js frontend
    |
    | HTTP / JSON / multipart upload
    v
FastAPI backend
    |
    +--> Session routes (/api/sessions/*)
    +--> Dataset routes (/api/datasets/*)
    +--> Legacy analysis routes (/api/upload, /api/analyze/*)
    |
    v
SessionService orchestration
    |
    +--> file parsing
    +--> local session store
    +--> Supabase persistence (optional)
    +--> AnalysisPipeline
             |
             +--> Data profiler
             +--> Semantic mapper
             +--> Query planner
             +--> Business metrics
             +--> EDA / quality / trends / correlations / outliers
             +--> ML prediction
             +--> XAI
             +--> Report narrator
             +--> Report generator
```

## Repository Shape

### `frontend/`

- `app/layout.tsx`: root layout and metadata.
- `app/page.tsx`: main client application. This is the current UI shell and contains landing, auth-like guest entry, chat, dataset, and dashboard views in one file.
- `lib/dataverse-api.ts`: typed API client for the session-based backend.
- `lib/apiConfig.ts`: backend URL normalization and health endpoint helpers.
- `scripts/dev.mjs`: one-command full-stack launcher used by `npm run dev`.
- `scripts/*.test.mjs`: frontend node-based smoke tests for dev wiring and API route usage.

### `dataverse_backend/app/`

- `main.py`: FastAPI entrypoint.
- `api/`: HTTP routes and request/response schemas.
- `agents/`: active two-agent wrappers (`DatasetAgent`, `AnalystAgent`) plus a few older agent files still present.
- `services/`: core business logic. This is the real center of the application.
- `db/`: old ORM models and a Supabase SQL migration copy.
- `core/`: config, logging, middleware, and storage helpers.

### `supabase/`

- `migrations/001_dataverse_schema.sql`: primary Supabase schema for the session-based app.

### `session_storage/` and `dataverse_backend/session_storage/`

- Local persistence and accumulated generated datasets, reports, and session artifacts.
- These are runtime outputs, not source code.

## Frontend Module Design

The frontend is currently functional but structurally concentrated.

### Active UI views inside `frontend/app/page.tsx`

- `LandingView`
- `SignUpView`
- `SignInView`
- `HomeView`
- `ChatView`
- `DataHubView`

### Active UI support components inside the same file

- `GlassCard`
- `FloatingInput`
- `ResultTable`
- `KpiStrip`
- `SimpleChart`

### Frontend data flow

```text
page.tsx
  -> dataverse-api.ts
    -> /api/sessions
    -> /api/sessions/{id}/datasets/upload
    -> /api/sessions/{id}/analyze
    -> /api/sessions/{id}/messages
    -> /api/datasets
    -> /api/sessions/{id}
```

The frontend also stores a workspace-scoped pseudo-user ID in local storage and sends it in `X-Dataverse-User` so recent sessions and datasets can be grouped for a browser workspace.

## Backend Module Design

## API Layer

### Active primary routes

- `session_routes.py`
  - create/list/get/update/delete chat sessions
  - upload dataset into a session
  - analyze session dataset
  - add chat message
  - list agent runs
  - list reports

- `dataset_session_routes.py`
  - compatibility endpoints for dataset listing, profile lookup, delete, and direct ask flow

- `report_routes.py`
  - report generation and report download

- `storage_routes.py`
  - storage mode status

### Legacy routes still mounted

- `routes.py`
  - `/api/health`
  - `/api/upload`
  - `/api/session/{session_id}`

- `analyze_routes.py`
  - `/api/analyze/upload`
  - `/api/analyze/query`

These legacy routes still work and are still covered by tests, so they are not dead code, but they are no longer the main frontend integration path.

## Service Layer

### Main active services

- `session_service.py`
  - overall session orchestration
  - dataset persistence
  - message persistence
  - report persistence
  - agent-run tracking
  - local/Supabase fallback logic

- `analysis_pipeline.py`
  - end-to-end analysis engine

- `semantic_mapper.py`
  - semantic role inference and dataset type detection

- `query_planner.py`
  - converts natural language into an intent plan

- `business_metrics.py`
  - revenue, profit, quantity, top products, category, region, customer, and expense summaries

- `data_quality.py`
  - data quality, EDA, trends, correlations, outliers, chart normalization

- `modeling.py`
  - prediction training

- `xai.py`
  - SHAP or feature-importance explainability

- `report_narrator.py`
  - executive summary and narrative sections

- `report_generator.py`
  - HTML and PDF report output

- `supabase_client.py`
  - backend-only REST and storage client, plus local JSON/file fallback

## Persistence Design

## Supabase flow

If Supabase is configured:

- Dataset binary files go to bucket `dataverse-datasets`
- Report HTML/PDF goes to bucket `dataverse-reports`
- Metadata rows are written to:
  - `chat_sessions`
  - `chat_messages`
  - `datasets`
  - `agent_runs`
  - `reports`

## Local fallback flow

If Supabase is not configured:

- JSON table snapshots are stored under `session_storage/dataverse_chat/*.json`
- Dataset/report files are stored under `session_storage/dataverse_chat/datasets` and `.../reports`
- Raw dataframes and semantic maps are also persisted in per-session directories via `session_store.py`

This fallback is useful for local development, but it can hide missing Supabase configuration because the app still appears to work.

## Analysis Flow

### Upload flow

```text
Upload file
  -> parse_uploaded_dataframe()
  -> persist_dataframe_for_dataset()
  -> profile_dataset()
  -> SemanticMapper.map_dataframe()
  -> store metadata and semantic map
```

### Question/analysis flow

```text
Question
  -> QueryPlanner.plan()
  -> calculate_business_metrics()
  -> compute_product_trends()
  -> compute_data_quality()
  -> compute_eda()
  -> compute_trends()
  -> compute_correlations()
  -> compute_outliers()
  -> train_prediction() if safe/requested
  -> explain_model()
  -> ReportNarrator
  -> optional ReportGenerator
```

## Dataset Intelligence Layer

The app supports semantic dataset typing rather than requiring one fixed schema.

### Dataset types recognized by `semantic_mapper.py`

- `mart_sales`
- `retail_sales`
- `invoice_sales`
- `ecommerce_orders`
- `pos_transactions`
- `transaction_ledger`
- `inventory`
- `food_dataset`
- `customer_sales`
- `generic_tabular`

### Special-case domain logic

- `ai_khata.py` handles AI Khata style transaction reports
- `analysis_pipeline.py` contains a food-dataset fallback path for non-sales food catalog datasets

## ML and XAI Architecture

### Prediction path

- safe target inference in `target_inference.py`
- task selection: regression vs classification
- candidate models:
  - `DummyRegressor`
  - `Ridge`
  - `RandomForestRegressor`
  - `DummyClassifier`
  - `LogisticRegression`
  - `RandomForestClassifier`

### XAI path

- prefer SHAP TreeExplainer for tree-compatible models
- otherwise use feature-importance fallback
- always return a plain-English explanation block

## LLM Architecture

`llm_provider.py` manages provider order and fallback.

### Providers supported in current code

- OpenAI
- Gemini
- Anthropic
- DeepAnalyze
- deterministic fallback

### Where LLMs are actually used

- semantic refinement in `SemanticMapper`
- query refinement in `QueryPlanner`
- report narration in `ReportNarrator`
- report sections in `ReportGenerator`
- chat title generation in `TitleGenerator`

### What LLMs do not do

- They do not compute revenue, profit, KPIs, trends, or prediction metrics.
- Those numbers come from backend code.

## Architecture Risks Found During Audit

### High

1. Mixed active and legacy backend paths:
   - session-based routes are the main app flow
   - legacy `/api/upload` and `/api/analyze/*` are still mounted

2. Schema duplication:
   - `supabase/migrations/001_dataverse_schema.sql`
   - `dataverse_backend/app/db/migrations/002_chat_sessions_supabase.sql`
   - these are similar but not identical

3. Stale architecture remnants:
   - several empty/legacy backend directories exist only because of `__pycache__`
   - old helper stacks remain beside the active flow

### Medium

1. `frontend/app/page.tsx` is a 2000+ line monolith.
2. `frontend/next.config.ts` ignores ESLint failures during production builds.
3. Local fallback can make Supabase misconfiguration harder to notice.
4. `dataverse_backend/app/db/models.py` does not reflect the active session metadata schema and is not used by the main runtime flow.

## Recommended Clean Target Structure

```text
frontend/
  app/
  lib/
  scripts/

dataverse_backend/
  app/
    api/
    agents/
    core/
    services/
  tests/

supabase/
  migrations/

docs/
  PROJECT_REPORT.md
  ARCHITECTURE.md
  TEACHER_EXPLANATION.md
  CLEANUP_REPORT.md
```

That target keeps the current architecture intact while removing stale caches, empty legacy directories, and misleading documentation.
