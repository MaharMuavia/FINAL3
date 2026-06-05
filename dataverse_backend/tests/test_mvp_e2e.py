"""End-to-end and integration tests for the AI Data Scientist MVP backend."""
from __future__ import annotations

import io
import random
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify that the health check endpoint returns 200 OK and healthy status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "message" in data


def test_csv_upload_works():
    """Verify that uploading a valid CSV file parses and returns profile + quality metadata."""
    csv_data = "date,product,category,quantity,revenue,cost\n2026-05-01,Product A,Electronics,5,500,300\n2026-05-02,Product B,Clothing,10,200,100"
    response = client.post(
        "/api/upload",
        files={"file": ("test.csv", csv_data, "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["filename"] == "test.csv"
    assert "dataset_profile" in data
    assert "data_quality" in data
    assert "message" in data


def test_excel_upload_works():
    """Verify that uploading a valid Excel spreadsheet is supported and profiled."""
    df = pd.DataFrame([
        {"date": "2026-05-01", "product": "Product A", "category": "Electronics", "quantity": 5, "revenue": 500, "cost": 300},
        {"date": "2026-05-02", "product": "Product B", "category": "Clothing", "quantity": 10, "revenue": 200, "cost": 100}
    ])
    excel_file = io.BytesIO()
    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    excel_file.seek(0)

    response = client.post(
        "/api/upload",
        files={"file": ("test.xlsx", excel_file.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["filename"] == "test.xlsx"
    assert "dataset_profile" in data


def test_empty_upload_returns_400():
    """Verify that uploading an empty file returns 400 Bad Request."""
    response = client.post(
        "/api/upload",
        files={"file": ("test.csv", b"", "text/csv")}
    )
    assert response.status_code == 400
    data = response.json()
    err_msg = data.get("detail", data.get("message", ""))
    assert "empty" in err_msg.lower()


def test_unsupported_file_returns_400():
    """Verify that uploading an unsupported file format (e.g. text/plain) returns 400."""
    response = client.post(
        "/api/upload",
        files={"file": ("test.txt", b"plain text data", "text/plain")}
    )
    assert response.status_code == 400
    data = response.json()
    err_msg = data.get("detail", data.get("message", ""))
    assert "supported" in err_msg.lower() or "csv" in err_msg.lower()


def test_analyze_upload_returns_expected_payload():
    """Verify analyze/upload returns profile, quality, charts, and recommendations."""
    csv_data = "date,product,category,quantity,revenue,cost\n" + "\n".join([f"2026-05-{i+1:02d},Product A,Electronics,5,500,300" for i in range(5)])
    response = client.post(
        "/api/analyze/upload",
        files={"file": ("test.csv", csv_data, "text/csv")},
        data={"use_llm": "false"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "filename" in data
    assert "dataset_profile" in data
    assert "data_quality" in data
    assert "semantic_map" in data
    assert "charts" in data
    assert "recommendations" in data
    assert "executive_summary" in data


def test_analyze_query_works_with_session():
    """Verify analyze/query successfully pulls from session and executes query."""
    # Step 1: Upload dataset to establish session_id
    csv_data = "date,product,category,quantity,revenue,cost\n" + "\n".join([f"2026-05-{i+1:02d},Product A,Electronics,5,500,300" for i in range(5)])
    upload_resp = client.post(
        "/api/analyze/upload",
        files={"file": ("test.csv", csv_data, "text/csv")},
        data={"use_llm": "false"}
    )
    assert upload_resp.status_code == 200
    session_id = upload_resp.json()["session_id"]

    # Step 2: Query the session
    query_resp = client.post(
        "/api/analyze/query",
        json={
            "session_id": session_id,
            "query": "What are my top selling products?",
            "use_llm": False
        }
    )
    assert query_resp.status_code == 200
    data = query_resp.json()
    assert data["session_id"] == session_id
    assert "query_answer" in data
    assert "executive_summary" in data


def test_prediction_skipped_for_small_dataset():
    """Verify that ML is skipped for datasets with fewer than 30 rows, explaining requirements."""
    # 15 rows (below threshold of 30)
    csv_data = "date,product,category,quantity,revenue,cost\n" + "\n".join([f"2026-05-{i+1:02d},Product A,Electronics,5,500,300" for i in range(15)])
    response = client.post(
        "/api/analyze/upload",
        files={"file": ("test_small.csv", csv_data, "text/csv")},
        data={"use_llm": "false", "run_predictions": "true"}
    )
    assert response.status_code == 200
    data = response.json()
    pred = data["prediction"]
    assert pred["status"] == "skipped"
    assert "fewer than" in pred["reason"]
    assert "required_columns_info" in pred
    assert "upload_requirements" in pred
    assert pred["upload_requirements"]["minimum_rows"] == 30
    assert "Prediction skipped" in " ".join(data["warnings"])


def test_prediction_runs_for_valid_dataset():
    """Verify that ML training executes successfully for datasets with >= 30 rows and target_column."""
    # Generate 35 diverse rows to support a valid stratified classification split or regression
    random.seed(42)
    rows = []
    for i in range(35):
        quantity = random.randint(1, 100)
        cost = random.randint(10, 50)
        revenue = quantity * 12 + cost + random.randint(-5, 5)
        category = "Electronics" if i % 2 == 0 else "Clothing"
        rows.append(f"2026-05-{i+1:02d},Product {chr(65 + i % 3)},{category},{quantity},{revenue},{cost}")
    csv_data = "date,product,category,quantity,revenue,cost\n" + "\n".join(rows)

    response = client.post(
        "/api/analyze/upload",
        files={"file": ("test_large.csv", csv_data, "text/csv")},
        data={
            "target_column": "revenue",
            "task_type": "regression",
            "run_predictions": "true",
            "run_xai": "false",
            "use_llm": "false"
        }
    )
    assert response.status_code == 200
    data = response.json()
    pred = data["prediction"]
    assert pred["status"] == "complete"
    assert pred["target_column"] == "revenue"
    assert pred["selected_model"] in {"Ridge", "RandomForestRegressor"}
    assert "test_metrics" in pred
    assert len(pred["predictions_sample"]) > 0


def test_llm_disabled_mode_returns_deterministic_report():
    """Verify that setting use_llm=False triggers the deterministic narrator fallback without model errors."""
    csv_data = "date,product,category,quantity,revenue,cost\n" + "\n".join([f"2026-05-{i+1:02d},Product A,Electronics,5,500,300" for i in range(5)])
    response = client.post(
        "/api/analyze/upload",
        files={"file": ("test.csv", csv_data, "text/csv")},
        data={"use_llm": "false"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["narration"]["narration_provider"] == "deterministic"
    assert "executive_summary" in data
    assert "Dataset contains 5 rows and 6 columns" in data["executive_summary"]
    assert len(data["key_insights"]) > 0
