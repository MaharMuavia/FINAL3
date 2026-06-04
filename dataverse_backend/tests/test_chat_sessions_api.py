from __future__ import annotations

from fastapi.testclient import TestClient

from dataverse_backend.app.main import app
from dataverse_backend.app.services.session_service import session_service
from dataverse_backend.app.services.supabase_client import LocalPersistence


def _csv_bytes() -> bytes:
    return (
        "date,product,revenue,quantity\n"
        "2026-05-01,A,100,2\n"
        "2026-05-02,B,150,3\n"
        "2026-05-03,A,125,1\n"
    ).encode("utf-8")


def test_session_upload_analysis_report_local_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(session_service.supabase, "url", "")
    monkeypatch.setattr(session_service.supabase, "service_role_key", None)
    monkeypatch.setattr(session_service, "local", LocalPersistence(tmp_path / "chat_store"))

    client = TestClient(app)

    created = client.post("/api/sessions", json={"title": "New Chat"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    uploaded = client.post(
        f"/api/sessions/{session_id}/datasets/upload",
        files={"file": ("may_sales.csv", _csv_bytes(), "text/csv")},
    )
    assert uploaded.status_code == 200
    dataset_id = uploaded.json()["dataset_id"]

    datasets = client.get("/api/datasets")
    assert datasets.status_code == 200
    assert any(item["id"] == dataset_id and item["session_id"] == session_id for item in datasets.json())

    analysis = client.post(
        f"/api/sessions/{session_id}/analyze",
        json={"dataset_id": dataset_id, "user_prompt": "Summarize sales", "run_xai": True, "generate_report": True},
    )
    assert analysis.status_code == 200
    body = analysis.json()
    assert [agent["name"] for agent in body["agents"]] == ["AnalysisAgent", "XAIReportAgent"]
    assert body["title"] != "New Chat"
    assert body["report"]["pdf_url"]
    assert body["report"]["html_url"]

    runs = client.get(f"/api/sessions/{session_id}/agent-runs")
    assert runs.status_code == 200
    assert [run["agent_name"] for run in runs.json()] == ["AnalysisAgent", "XAIReportAgent"]
