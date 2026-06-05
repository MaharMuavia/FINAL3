# DataVerse AI Data Scientist Backend (MVP)

DataVerse AI is a clean, production-ready MVP for an AI Data Scientist backend using FastAPI. It parses datasets (CSV/XLSX), validates columns, normalizes headers, computes business metrics deterministically using Pandas/scikit-learn, and produces a professional data report.

The LLM is optional and only used to polish the narration of computed facts. All calculations are deterministic.

## Two-Agent Architecture

The MVP relies on exactly two agents:
1. **`DatasetAgent`** (`app/agents/dataset_agent.py`):
   - Validates uploaded file limits and file formats.
   - Parses CSV/XLSX safely.
   - Normalizes columns (headers are cleaned and whitespace is removed).
   - Generates a unique `session_id`.
   - Stores the dataset locally in the filesystem session store.
   - Produces a dataset profile and data quality summary.
2. **`AnalystAgent`** (`app/agents/analyst_agent.py`):
   - Understands user semantic queries.
   - Maps columns semantically (e.g. mapping date, products, revenue).
   - Computes business metrics, EDA, trends, correlations, and outlier flags using Pandas.
   - Triggers predictive machine learning (Ridge or RandomForest) only if the dataset has at least **30 rows** (`MIN_ROWS_FOR_PREDICTION`) and a target is provided.
   - Runs XAI (Shapley/Feature Importance) upon successful modeling.
   - Generates charts-ready JSON and final polished report narration (using offline deterministic narration if LLM keys are absent).

---

## Simple Setup

### 1. Configure Environment
Create a local `.env` file inside the `dataverse_backend` folder:
```powershell
copy dataverse_backend\.env.example dataverse_backend\.env
```

### 2. Install MVP Requirements
Ensure your virtual environment is active, then install the lightweight MVP dependencies:
```powershell
.\.venv\Scripts\python -m pip install -r dataverse_backend/requirements-mvp.txt
```

### 3. Run Backend Server
Start the FastAPI server from the `dataverse_backend` directory:
```powershell
cd dataverse_backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Or run directly from the workspace root directory:
```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir dataverse_backend
```

---

## API Endpoints

The MVP exposes exactly 6 endpoints:
- `GET /api/health` — API health check.
- `POST /api/upload` — Uploads and profiles a dataset.
- `GET /api/session/{session_id}` — Loads a profiled session.
- `DELETE /api/session/{session_id}` — Deletes session storage.
- `POST /api/analyze/upload` — Uploads and immediately runs full reports.
- `POST /api/analyze/query` — Runs a semantic query against an existing session.

---

## Testing with Curl

### 1. Upload a Dataset for Profiling
```powershell
curl.exe http://127.0.0.1:8000/api/upload -F "file=@sample_small_dataset.csv"
```

### 2. Run Full Analysis Upload
```powershell
curl.exe -X POST http://127.0.0.1:8000/api/analyze/upload `
  -F "file=@sample_sales.csv" `
  -F "target_column=revenue" `
  -F "task_type=regression" `
  -F "run_predictions=true" `
  -F "run_xai=true" `
  -F "use_llm=false"
```

### 3. Query an Existing Session
```powershell
curl.exe -X POST http://127.0.0.1:8000/api/analyze/query `
  -H "Content-Type: application/json" `
  -d "{\"session_id\":\"YOUR_SESSION_ID\",\"query\":\"What are my top selling products?\",\"target_column\":\"revenue\",\"run_predictions\":true,\"use_llm\":false}"
```

---

## Expected Response Shapes

### POST `/api/analyze/upload` Response
```json
{
  "session_id": "0bde26cd-21cd-413b-bf64-b968ee631007",
  "filename": "sample_sales.csv",
  "dataset_profile": {
    "row_count": 40,
    "column_count": 6,
    "columns": ["date", "product", "category", "quantity", "revenue", "cost"],
    "dtypes": {"date": "object", "product": "object", "category": "object", "quantity": "int64", "revenue": "int64", "cost": "int64"}
  },
  "data_quality": {
    "data_quality_score": 1.0,
    "missing_cells": 0,
    "duplicate_rows": 0,
    "warnings": []
  },
  "semantic_map": {
    "dataset_type": "transaction_ledger",
    "column_roles": {
      "date": "timestamp",
      "product": "category",
      "category": "category",
      "quantity": "quantity",
      "revenue": "revenue",
      "cost": "cost"
    }
  },
  "business_metrics": {
    "total_revenue": 21630,
    "total_profit": 11330,
    "gross_margin": 0.5238
  },
  "query_answer": {
    "answer": "Dataset uploaded and analyzed.",
    "facts": {}
  },
  "eda": {
    "summary": {
      "quantity": {"mean": 6.8, "min": 2, "max": 15},
      "revenue": {"mean": 472.5, "min": 100, "max": 1200}
    }
  },
  "trends": {
    "series": [
      {"value_column": "revenue", "direction": "upward", "slope": 3.4}
    ]
  },
  "correlations": {
    "strong_pairs": [
      {"column_a": "quantity", "column_b": "revenue", "correlation": 0.98}
    ]
  },
  "outliers": {
    "total_outlier_cells": 0
  },
  "prediction": {
    "status": "complete",
    "task_type": "regression",
    "target_column": "revenue",
    "selected_model": "Ridge",
    "test_metrics": {"rmse": 12.34, "r2": 0.99},
    "predictions_sample": []
  },
  "xai": {
    "status": "complete",
    "plain_english_explanation": "Quantity is the strongest driver of Revenue..."
  },
  "charts": [
    {"type": "line", "title": "Sales revenue by month", "x": "period", "y": "sales_revenue", "data": []}
  ],
  "executive_summary": "Dataset contains 40 rows. Total revenue is 21630...",
  "key_insights": [
    "Dataset contains 40 rows and 6 columns.",
    "Total revenue is 21630."
  ],
  "recommendations": [
    "Review missing values before operational decisions."
  ],
  "warnings": [],
  "next_questions": [
    "Which target column should be optimized next?"
  ]
}
```

---

## Verification Tests

Run the full end-to-end test suite:
```powershell
cd dataverse_backend
..\.venv\Scripts\python -m pytest -v tests/test_mvp_e2e.py
```
All 10 test scenarios are validated and pass successfully in the local execution context.
