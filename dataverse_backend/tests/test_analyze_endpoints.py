from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app


def _sample_frame(rows: int = 36) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=rows, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "region": ["North", "South", "East"] * (rows // 3),
            "category": ["A", "B", "A"] * (rows // 3),
            "price": [10 + (idx % 5) for idx in range(rows)],
            "quantity": [1 + (idx % 4) for idx in range(rows)],
            "revenue": [100 + idx * 7 for idx in range(rows)],
            "churned": ["yes" if idx % 4 == 0 else "no" for idx in range(rows)],
        }
    )


def _post_upload(client: TestClient, df: pd.DataFrame, filename: str):
    if filename.endswith(".csv"):
        body = df.to_csv(index=False).encode("utf-8")
        mime = "text/csv"
    else:
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        body = buffer.getvalue()
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return client.post(
        "/api/analyze/upload",
        files={"file": (filename, body, mime)},
    )


def test_csv_upload_runs_full_analysis_without_auth():
    with TestClient(app) as client:
        response = _post_upload(client, _sample_frame(), "sales.csv")

    assert response.status_code == 200
    payload = response.json()
    expected_keys = {
        "session_id",
        "dataset_profile",
        "column_roles",
        "eda",
        "trends",
        "correlations",
        "outliers",
        "charts",
        "target_suggestions",
        "automl",
        "xai",
        "executive_summary",
        "recommendations",
        "warnings",
    }
    assert expected_keys <= payload.keys()
    assert payload["dataset_profile"]["row_count"] == 36
    assert payload["eda"]["missing_values"]["total_missing"] == 0
    session_dir = Path("session_storage") / payload["session_id"]
    assert (session_dir / "dataset.parquet").exists() or (session_dir / "dataset.pkl").exists()


def test_excel_upload_runs_full_analysis():
    with TestClient(app) as client:
        response = _post_upload(client, _sample_frame(), "sales.xlsx")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_profile"]["column_count"] == 7
    assert payload["trends"]["date_columns"]
    assert payload["charts"]


def test_query_uses_existing_uploaded_dataset_and_selected_target():
    with TestClient(app) as client:
        upload = _post_upload(client, _sample_frame(), "sales.csv")
        session_id = upload.json()["session_id"]
        response = client.post(
            "/api/analyze/query",
            json={
                "session_id": session_id,
                "query": "predict sales revenue and explain important features",
                "target_column": "revenue",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["automl"]["status"] == "success"
    assert payload["automl"]["target_column"] == "revenue"
    assert payload["xai"]["status"] in {"success", "fallback"}


def test_analysis_pipeline_detects_missing_values_and_trends():
    from app.services.analysis_pipeline import AnalysisPipeline

    df = _sample_frame()
    df.loc[0, "region"] = None

    report = AnalysisPipeline().run_full_analysis(df, query="analyze this dataset")

    assert report["eda"]["missing_values"]["columns"]["region"]["count"] == 1
    assert report["trends"]["date_columns"] == ["date"]
    assert report["trends"]["series"]


def test_target_suggestion_filters_ids_and_finds_regression_and_classification_targets():
    from app.services.target_inference import suggest_targets

    df = _sample_frame()
    df["customer_id"] = [f"C-{idx:04d}" for idx in range(len(df))]
    suggestions = suggest_targets(df)

    names = {item["column"]: item["task_type"] for item in suggestions}
    assert names["revenue"] == "regression"
    assert names["churned"] == "classification"
    assert "customer_id" not in names


def test_target_inference_maps_predict_sales_keywords():
    from app.services.target_inference import infer_target_column

    target = infer_target_column(_sample_frame(), query="predict sales next month")

    assert target is not None
    assert target["column"] == "revenue"
    assert target["task_type"] == "regression"


def test_regression_automl_trains_with_numeric_target():
    from app.services.analysis_pipeline import AnalysisPipeline

    report = AnalysisPipeline().run_full_analysis(_sample_frame(), target_column="revenue")

    assert report["automl"]["status"] == "success"
    assert report["automl"]["task_type"] == "regression"
    assert "metrics" in report["automl"]


def test_classification_automl_trains_with_categorical_target():
    from app.services.analysis_pipeline import AnalysisPipeline

    report = AnalysisPipeline().run_full_analysis(_sample_frame(), target_column="churned")

    assert report["automl"]["status"] == "success"
    assert report["automl"]["task_type"] == "classification"
    assert "metrics" in report["automl"]


def test_llm_unavailable_uses_deterministic_report_narrator():
    from app.services.report_narrator import ReportNarrator

    class BrokenProvider:
        async def generate(self, prompt: str):
            raise RuntimeError("network unavailable")

    result = ReportNarrator(llm_provider=BrokenProvider()).narrate(
        {
            "dataset_profile": {"row_count": 36, "column_count": 7},
            "eda": {"missing_values": {"total_missing": 2}},
            "target_suggestions": [{"column": "revenue", "task_type": "regression"}],
            "warnings": [],
        }
    )

    assert "36 rows" in result["executive_summary"]
    assert result["recommendations"]


def test_xai_falls_back_to_feature_importance_when_shap_fails(monkeypatch):
    from app.services import analysis_pipeline
    from app.services.analysis_pipeline import AnalysisPipeline

    monkeypatch.setattr(analysis_pipeline, "SHAP_AVAILABLE", False)

    report = AnalysisPipeline().run_full_analysis(_sample_frame(), target_column="revenue")

    assert report["automl"]["status"] == "success"
    assert report["xai"]["status"] == "fallback"
    assert report["xai"]["method"] == "feature_importance"


def test_ai_khata_report_analysis_uses_extracted_business_summary():
    from app.api.upload_parsing import parse_uploaded_dataframe
    from app.services.analysis_pipeline import AnalysisPipeline

    csv_bytes = (
        b'"AI Khata Report"\n'
        b'"Shop Name","Muhammad Muavia"\n'
        b'"Report Filter","all"\n'
        b'"Generated At","2026-05-01 11:43:47"\n'
        b'\n'
        b'"Summary"\n'
        b'"Total Sales","7000"\n'
        b'"Total Expenses","500"\n'
        b'"Udhaar Outstanding","500"\n'
        b'"Net Profit","6500"\n'
        b'"Profit Status","Profit"\n'
        b'\n'
        b'"Transaction Details"\n'
        b'"Date","Time","Category","Item/Customer","Amount (Rs)"\n'
        b'"2026-05-01","11:43:40","UDHAAR","Ali","500"\n'
        b'"2026-05-01","11:43:23","EXPENSE","Rent","500"\n'
        b'"2026-05-01","11:43:10","SALES","General Entry","5000"\n'
        b'"2026-05-01","11:43:05","SALES","burger","2000"\n'
    )
    df = parse_uploaded_dataframe("AI_Khata_report.csv", csv_bytes)

    report = AnalysisPipeline().run_full_analysis(df, query="tell me about the given data")

    assert report["dataset_profile"]["report_metadata"]["Shop Name"] == "Muhammad Muavia"
    assert report["dataset_profile"]["report_summary"]["Total Sales"] == "7000"
    assert report["dataset_profile"]["dataset_type"] == "ai_khata_transaction_report"
    assert report["column_roles"]["Amount (Rs)"] == "transaction_amount"
    assert report["column_roles"]["Item/Customer"] == "conditional_item_customer"
    assert report["business_summary"] == {
        "shop_name": "Muhammad Muavia",
        "report_filter": "all",
        "generated_at": "2026-05-01 11:43:47",
        "total_sales": 7000,
        "total_expenses": 500,
        "udhaar_outstanding": 500,
        "net_profit": 6500,
        "profit_status": "Profit",
        "transaction_count": 4,
        "sales_transaction_count": 2,
        "expense_transaction_count": 1,
        "udhaar_transaction_count": 1,
    }
    assert report["trends"]["business_revenue_by_month"] == [{"period": "2026-05", "sales_revenue": 7000}]
    assert report["prediction"]["status"] == "skipped"
    assert "fewer than 30 rows" in report["prediction"]["reason"]
    assert "sales Rs 7000" in report["executive_summary"]
