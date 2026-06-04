# DataVerse AI (Backend-Only)

DataVerse AI is now configured as a backend-only analytics platform.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy async ORM
- PostgreSQL (asyncpg)
- Redis
- Celery
- Pandas, NumPy, scikit-learn, SHAP

## Project Layout

```text
.
|-- dataverse_backend/
|   |-- app/
|   |   |-- api/                 FastAPI route modules
|   |   |-- agents/              Analysis/orchestration agents
|   |   |-- core/                Config, auth, middleware, logging
|   |   |-- db/                  SQLAlchemy models and database setup
|   |   |-- services/            Billing/model catalog services
|   |   |-- state/               Session state stores
|   |   `-- main.py              Backend entrypoint
|   |-- tests/                   Backend tests
|   `-- requirements.txt         Python dependencies
|-- docker-compose.yml           Local backend services
|-- docker-compose.prod.yml      Production backend services
`-- .env.example                 Root environment example
```

## Environment Setup

From project root:

```powershell
copy .env.example .env
copy dataverse_backend\.env.example dataverse_backend\.env
```

If virtual environment is missing:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
```

Install backend dependencies:

```powershell
.\.venv\Scripts\python -m pip install -r dataverse_backend\requirements.txt
```

OpenAI, Gemini, Anthropic, and DeepAnalyze keys are optional. The analysis core
does profiling, EDA, trend detection, correlation analysis, prediction, chart
spec generation, and XAI without any external API key. LLM providers are used
only to polish narration from computed facts. If none are configured, the API
still returns a deterministic executive summary and recommendations.

Useful `.env` values:

```text
LLM_PROVIDER=auto
OPENAI_API_KEY=
OPENAI_CHAT_MODEL=gpt-4o
GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-flash
ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-3-5-sonnet-20241022
DEEPANALYZE_API_KEY=
DEEPANALYZE_API_BASE=
DEEPANALYZE_LOCAL_BASE_URL=http://localhost:8000/v1
DEEPANALYZE_MODEL=DeepAnalyze-8B
REPORT_NARRATOR_TIMEOUT_SECONDS=20
AUTO_TRAIN_TARGET_CONFIDENCE=0.65
MIN_ROWS_FOR_PREDICTION=30
DATABASE_STARTUP_CHECK_ENABLED=false
```

Leave `DATABASE_STARTUP_CHECK_ENABLED=false` for local/demo analysis when
PostgreSQL is not running. Enable it in production when the app should ensure DB
tables during startup.

## Run Locally

```powershell
cd C:\Users\mouav\OneDrive\Desktop\FINAL3\dataverse_backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Alternative from root:

```powershell
cd C:\Users\mouav\OneDrive\Desktop\FINAL3
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir dataverse_backend
```

## Health Checks

```powershell
curl.exe http://127.0.0.1:8000/api/health
curl.exe http://127.0.0.1:8000/health/live
curl.exe http://127.0.0.1:8000/health/ready
```

## Docker Compose

```powershell
cd C:\Users\mouav\OneDrive\Desktop\FINAL3
copy .env.example .env
docker compose up --build
```

Main services:

- Backend API: http://localhost:8000
- PostgreSQL: internal to the Docker Compose network
- Redis: internal to the Docker Compose network
- Only the backend and frontend are published on the host by default

## Useful API Examples

Upload a file for a lightweight profile:

```powershell
curl.exe -F "file=@sample_products_smoke_test.xlsx" http://127.0.0.1:8000/api/upload
```

Upload and immediately run the full AI data analyst report:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/analyze/upload `
  -F "file=@sample_products_smoke_test.xlsx" `
  -F "target_column=revenue" `
  -F "task_type=regression" `
  -F "run_predictions=true" `
  -F "run_xai=true" `
  -F "use_llm=false"
```

Ask a query against an uploaded analysis session:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/analyze/query `
  -H "Content-Type: application/json" `
  -d "{\"session_id\":\"YOUR_SESSION_ID\",\"query\":\"predict sales revenue and explain the drivers\",\"target_column\":\"revenue\",\"run_predictions\":true,\"run_xai\":true,\"use_llm\":false}"
```

`POST /api/analyze/upload` returns a clean JSON report with:

- `session_id`, `filename`
- `dataset_profile`, `data_quality`, `eda`, `trends`, `correlations`, `outliers`
- `semantic_map`, `business_metrics`, `query_plan`, `query_answer`
- `target_suggestions`, `prediction`, `xai`, `charts`
- `executive_summary`, `key_insights`, `recommendations`, `warnings`, `next_questions`, `report_sections`

The semantic layer maps business meaning first, then Pandas calculates final numbers. For transaction ledgers with sale/expense/credit/refund row types, revenue uses the mapped sales filter instead of summing every amount row.

DeepAnalyze can run as a remote OpenAI-compatible service:

```text
LLM_PROVIDER=deepanalyze
DEEPANALYZE_API_KEY=your-key
DEEPANALYZE_API_BASE=https://your-deepanalyze-host/v1
DEEPANALYZE_MODEL=DeepAnalyze-8B
```

Or as a local OpenAI-compatible service:

```text
LLM_PROVIDER=deepanalyze
DEEPANALYZE_LOCAL_BASE_URL=http://localhost:8000/v1
DEEPANALYZE_MODEL=DeepAnalyze-8B
```

The local/demo analysis endpoints do not require JWT. Production deployments
should mount them behind workspace authorization before exposing user datasets.

Run streaming query:

```powershell
curl.exe -N "http://127.0.0.1:8000/api/stream/query?session_id=YOUR_SESSION_ID&query=show%20summary"
```

## Analysis Smoke Test

Run the pipeline directly without external LLM keys:

```powershell
.\.venv\Scripts\python scripts\smoke_test_analysis.py
```

## Tests

```powershell
.\.venv\Scripts\python -m pytest dataverse_backend\tests -q
```
