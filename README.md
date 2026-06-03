# DataVerse AI (Backend-Only)

DataVerse AI is now configured as a backend-only analytics platform.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy async ORM
- PostgreSQL (asyncpg)
- Redis
- Celery
- Pandas, NumPy, scikit-learn

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

OpenAI, Gemini, and Anthropic keys are optional. When keys are available the
report narrator tries OpenAI first, then Gemini, then Anthropic, then local
DeepAnalyze/Ollama. If none are reachable, the API still returns a deterministic
executive summary from computed facts.

Useful `.env` values:

```text
OPENAI_API_KEY=optional
GEMINI_API_KEY=optional
ANTHROPIC_API_KEY=optional
DEEPANALYZE_BASE_URL=http://localhost:11434
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

Upload a file:

```powershell
curl.exe -F "file=@sample_products_smoke_test.xlsx" http://127.0.0.1:8000/api/upload
```

Upload and immediately run the full AI data analyst report:

```powershell
curl.exe -F "file=@sample_products_smoke_test.xlsx" http://127.0.0.1:8000/api/analyze/upload
```

Ask a query against an uploaded analysis session:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/analyze/query `
  -H "Content-Type: application/json" `
  -d "{\"session_id\":\"YOUR_SESSION_ID\",\"query\":\"predict sales revenue and explain the drivers\",\"target_column\":\"revenue\"}"
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
