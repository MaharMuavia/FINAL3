# DataVerse AI Project Report

## 1. Title

DataVerse AI: An AI-Assisted Data Analyst Web Application for Natural Language Dataset Exploration

## 2. Abstract

DataVerse AI is a full-stack web application that allows a user to upload a CSV or Excel dataset and ask questions in natural language. The system analyzes the data like a junior-to-mid-level business analyst by combining deterministic analytics, optional large language model assistance, machine learning prediction, explainable AI, and downloadable reports. The frontend is built in Next.js, the backend is built in FastAPI, dataset computation is handled with pandas and scikit-learn, and metadata can be persisted either in Supabase or in a local fallback store for development.

## 3. Problem Statement

Many users have spreadsheet data but cannot easily write SQL, Python, or dashboards. They need a system that can:

- accept raw datasets quickly
- understand what the columns mean
- answer business questions in plain language
- show results as tables and charts
- provide predictions when possible
- explain model behavior clearly
- export findings into a professional report

Traditional BI tools require manual modeling and dashboard design. DataVerse AI aims to reduce that barrier.

## 4. Objectives

- build an interface where users can upload data and chat with it
- infer dataset meaning automatically
- compute reliable business metrics with deterministic code
- support prediction and explainability when the dataset is suitable
- generate downloadable HTML/PDF reports
- support cloud persistence with a local development fallback

## 5. Proposed Solution

The proposed solution is a session-based AI analytics application with two major layers:

- a Next.js frontend for upload, chat, charts, and reports
- a FastAPI backend that parses files, profiles data, interprets questions, computes analytics, trains models, generates XAI, and stores session metadata

The design deliberately uses LLMs only for language-oriented tasks such as narration and semantic refinement. Numeric outputs are calculated by backend code.

## 6. Technologies Used

### Frontend

- Next.js App Router
- React 19
- TypeScript
- Tailwind CSS v4
- Lucide React icons
- Motion

### Backend

- Python
- FastAPI
- Uvicorn
- pandas
- NumPy
- scikit-learn
- SHAP
- ReportLab
- Jinja2
- httpx

### Storage and persistence

- Supabase REST and Storage APIs
- local JSON/file fallback persistence
- filesystem session store for datasets and semantic maps

### Optional AI providers

- OpenAI
- Gemini
- Anthropic
- DeepAnalyze
- deterministic fallback mode

## 7. Frontend Explanation

The frontend lives in `frontend/`.

### Important files

- `frontend/app/layout.tsx`: global layout and metadata
- `frontend/app/page.tsx`: main application UI
- `frontend/lib/dataverse-api.ts`: typed client for backend routes
- `frontend/lib/apiConfig.ts`: API base URL and health URL logic
- `frontend/scripts/dev.mjs`: full-stack launcher used by `npm run dev`

### What the frontend does

- shows the landing page and guest entry
- creates sessions
- uploads datasets
- runs automatic analysis
- sends follow-up questions
- renders chat answers, tables, charts, KPI cards, and report links
- lists recent sessions and recent datasets

### Structural note

The frontend currently works, but `frontend/app/page.tsx` is very large and combines many screens and components in one file. This is a maintainability issue, not a functional blocker.

## 8. Backend Explanation

The backend lives in `dataverse_backend/app/`.

### Entry point

- `dataverse_backend/app/main.py`

### Main API route files

- `api/session_routes.py`: primary session-based chat flow
- `api/dataset_session_routes.py`: dataset listing/profile/ask compatibility flow
- `api/report_routes.py`: report generation/download
- `api/storage_routes.py`: storage mode status
- `api/routes.py`: legacy upload/session routes
- `api/analyze_routes.py`: legacy analysis routes

### Main service files

- `services/session_service.py`: session orchestration
- `services/analysis_pipeline.py`: analysis engine
- `services/semantic_mapper.py`: semantic role inference
- `services/query_planner.py`: intent planning
- `services/business_metrics.py`: revenue/profit/category/product/customer logic
- `services/data_quality.py`: quality, EDA, trends, correlations, outliers
- `services/modeling.py`: prediction path
- `services/xai.py`: explainability path
- `services/report_narrator.py`: narrative text
- `services/report_generator.py`: HTML and PDF report output
- `services/supabase_client.py`: Supabase + local fallback persistence

## 9. Supabase Explanation

Supabase is optional in the current code, but it is the intended cloud persistence layer.

### Required Supabase environment variables

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_ANON_KEY` is configured but not required by the current backend-only persistence flow
- `SUPABASE_DATASET_BUCKET`
- `SUPABASE_REPORT_BUCKET`

### Tables used by the app

- `chat_sessions`
- `chat_messages`
- `datasets`
- `agent_runs`
- `reports`

### Storage buckets

- `dataverse-datasets`
- `dataverse-reports`

### Important behavior

If Supabase is not configured, the app automatically falls back to local storage. This is useful for development but can hide missing Supabase setup because the app still appears to work.

## 10. AI / ML Models Used

## LLM models used in the project

### OpenAI

- configured model: `gpt-4o-mini`
- used for:
  - narration
  - semantic/query refinement
  - title generation

### Gemini

- configured models:
  - `gemini-1.5-flash`
  - `gemini-1.5-pro`
- used as optional fallback for narration and text generation

### Anthropic

- configured model: `claude-sonnet-4-6` in `config.py`
- `.env.example` still mentions `claude-3-5-sonnet-20241022`
- used as optional narration/text fallback

### DeepSeek

- configured model: `deepseek-chat`
- used through configuration, mainly as an optional provider path

### DeepAnalyze

- configured models:
  - `deepanalyze-8b`
  - fallback `phi3:mini`
- used only if a DeepAnalyze endpoint is configured

### Configured but not actively used in the main flow

- Mistral variables exist in the root `.env.example`, but there is no active runtime use in the audited app code
- Redis/Celery and MinIO/S3 variables exist in config, but the main current flow does not use background workers or alternate object storage

## ML models used

### Regression

- `DummyRegressor`
- `Ridge`
- `RandomForestRegressor`

### Classification

- `DummyClassifier`
- `LogisticRegression`
- `RandomForestClassifier`

### XAI

- SHAP TreeExplainer when possible
- feature importance fallback otherwise

## 11. Datasets Used / Supported

### File formats

- CSV
- XLSX
- XLS

### Dataset types supported by the semantic layer

- mart sales
- retail sales
- invoice sales
- ecommerce orders
- POS transactions
- transaction ledger
- inventory
- food dataset
- customer sales
- generic tabular data
- AI Khata style transaction reports through a special helper path

### Example retail dataset columns used in tests

- `order_id`
- `order_datetime`
- `store_id`
- `region`
- `city`
- `product_id`
- `category`
- `subcategory`
- `unit_price`
- `quantity`
- `discount`
- `total_sales`
- `profit`
- `customer_id`
- `customer_type`
- `payment_method`
- `online_order`
- `stockout_flag`
- `weekday`
- `month`

### What the system can calculate from a good retail dataset

- total sales
- total quantity
- total profit
- gross margin
- top products
- category performance
- region performance
- monthly revenue trends
- customer summaries
- prediction
- XAI

### What it cannot calculate when columns are missing

- no revenue analysis without a revenue/amount/price-based metric
- no time trend without a usable date column
- no most-sold product without product plus quantity or sales evidence
- no prediction when the dataset is too small or the target is unsafe

## 12. Data Analysis Workflow

```text
User uploads file
-> frontend sends multipart request to backend
-> backend parses CSV/Excel
-> backend stores file/metadata locally or in Supabase
-> semantic mapper detects column meaning and dataset type
-> data quality + EDA + business metrics are computed
-> query planner interprets the user question
-> pandas/scikit-learn compute the result
-> charts/tables/KPIs are prepared
-> narration is generated
-> frontend displays answer
```

## 13. Prediction Workflow

```text
check row count
-> infer or confirm target column
-> decide regression vs classification
-> build safe feature set
-> remove identifiers, constants, leakage-like columns
-> train baseline + candidate models
-> choose best non-dummy model by score
-> return metrics, sample predictions, and feature importance
```

### Prediction rules

- minimum rows: `MIN_ROWS_FOR_PREDICTION`, default `30`
- predictions can also auto-run if a target is inferred with enough confidence
- target inference lives in `target_inference.py`

## 14. XAI Workflow

```text
trained model available?
-> yes:
   if tree-compatible and SHAP works -> SHAP global/local explanations
   else -> feature importance fallback
-> no:
   return skipped/fallback explanation
```

The system always attempts to return a plain-English explanation block so the user understands the result.

## 15. Report Generation Workflow

```text
analysis facts
-> ReportNarrator produces summary and section content
-> ReportGenerator builds self-contained HTML
-> ReportGenerator builds PDF
-> report files stored in Supabase or local reports folder
-> frontend receives download URLs
```

## 16. System Architecture

```text
Next.js frontend
  -> FastAPI routes
    -> SessionService
      -> AnalysisPipeline
        -> semantic mapper
        -> query planner
        -> business metrics
        -> data quality / EDA
        -> prediction
        -> XAI
        -> narration
        -> report generation
      -> Supabase or local persistence
```

## 17. API Endpoints

### Main active endpoints

- `GET /health/live`
- `GET /api/health`
- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `PATCH /api/sessions/{session_id}`
- `DELETE /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/datasets/upload`
- `GET /api/sessions/{session_id}/datasets`
- `POST /api/sessions/{session_id}/analyze`
- `POST /api/sessions/{session_id}/messages`
- `GET /api/sessions/{session_id}/agent-runs`
- `GET /api/sessions/{session_id}/reports`
- `POST /api/sessions/{session_id}/reports/generate`
- `GET /api/reports/{report_id}/download`
- `GET /api/datasets`
- `GET /api/datasets/{dataset_id}`
- `GET /api/datasets/{dataset_id}/profile`
- `POST /api/datasets/{dataset_id}/ask`
- `DELETE /api/datasets/{dataset_id}`
- `GET /api/storage/status`

### Legacy endpoints still mounted

- `POST /api/upload`
- `GET /api/session/{session_id}`
- `DELETE /api/session/{session_id}`
- `POST /api/analyze/upload`
- `POST /api/analyze/query`

## 18. Results / Output Examples

The application can return:

- plain-language answer text
- KPI cards
- ranked tables
- simple chart payloads for line/bar/pie/donut renderings
- prediction metrics
- feature importance / SHAP-style output
- warning lists
- recommendations
- downloadable report links

## 19. Limitations

- frontend UI is concentrated in one large file
- multiple legacy and active backend paths coexist
- Supabase schema is duplicated in two SQL files
- local fallback can hide persistence misconfiguration
- some helper files and test paths represent older architecture, not the main frontend flow
- charts are custom/simple and not yet a full charting system
- build currently ignores ESLint errors

## 20. Future Work

- split `frontend/app/page.tsx` into reusable components
- unify around one API surface and retire legacy routes
- keep only one canonical Supabase schema definition
- make storage mode more explicit in the UI
- add stronger end-to-end browser tests
- improve charting and dashboard exploration
- add role-based auth and user-level RLS policies for direct Supabase use

## 21. How to Run the Project

### Backend setup

```powershell
copy dataverse_backend\.env.example dataverse_backend\.env
.\.venv\Scripts\python -m pip install -r dataverse_backend\requirements.txt
```

### Frontend setup

```powershell
cd frontend
npm install
```

### Run both together from the repository root

```powershell
npm run dev
```

This starts:

- FastAPI on `http://127.0.0.1:8000`
- Next.js on `http://127.0.0.1:3000`

### Run manually in two terminals

Terminal 1:

```powershell
cd dataverse_backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm run dev:next
```

## 22. Conclusion

DataVerse AI successfully combines web development, data engineering, machine learning, explainable AI, and report generation into one applied final-year project. Its strongest design choice is that it uses deterministic computation for business results and uses LLMs only to improve understanding and communication. The current codebase is functional and demonstrates meaningful full-stack AI analytics work, but it also contains legacy layers and structure drift that should be cleaned to make the project easier to explain, maintain, and defend academically.
