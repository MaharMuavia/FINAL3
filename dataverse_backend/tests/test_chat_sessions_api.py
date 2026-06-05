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
        f"/api/sessions/{session_id}/datasets/upload?auto_analyze=false",
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
    assert [agent["name"] for agent in body["agents"]] == ["DatasetAgent", "AnalystAgent"]
    assert body["title"] != "New Chat"
    assert body["report"]["pdf_url"]
    assert body["report"]["html_url"]
    html_report = client.get(f"/api/reports/{body['report']['report_id']}/download?format=html")
    pdf_report = client.get(f"/api/reports/{body['report']['report_id']}/download?format=pdf")
    assert html_report.status_code == 200
    assert "<svg" in html_report.text
    assert pdf_report.status_code == 200
    assert len(pdf_report.content) > 1000

    runs = client.get(f"/api/sessions/{session_id}/agent-runs")
    assert runs.status_code == 200
    assert [run["agent_name"] for run in runs.json()] == ["DatasetAgent", "AnalystAgent"]
    assert all(run["output"].get("steps") for run in runs.json())


def test_session_upload_profiles_only_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(session_service.supabase, "url", "")
    monkeypatch.setattr(session_service.supabase, "service_role_key", None)
    monkeypatch.setattr(session_service, "local", LocalPersistence(tmp_path / "chat_store"))

    client = TestClient(app)
    session_id = client.post("/api/sessions", json={"title": "New Chat"}).json()["session_id"]
    uploaded = client.post(
        f"/api/sessions/{session_id}/datasets/upload",
        files={"file": ("small_sales.csv", _csv_bytes(), "text/csv")},
    )

    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["analysis"] is None

    runs = client.get(f"/api/sessions/{session_id}/agent-runs")
    assert runs.json() == []


def test_recent_sidebar_data_is_scoped_to_workspace_user(tmp_path, monkeypatch):
    monkeypatch.setattr(session_service.supabase, "url", "")
    monkeypatch.setattr(session_service.supabase, "service_role_key", None)
    monkeypatch.setattr(session_service, "local", LocalPersistence(tmp_path / "chat_store"))

    client = TestClient(app)
    user_a = "11111111-1111-4111-8111-111111111111"
    user_b = "22222222-2222-4222-8222-222222222222"

    session_a = client.post("/api/sessions", json={"title": "User A"}, headers={"X-Dataverse-User": user_a}).json()["session_id"]
    session_b = client.post("/api/sessions", json={"title": "User B"}, headers={"X-Dataverse-User": user_b}).json()["session_id"]
    uploaded = client.post(
        f"/api/sessions/{session_a}/datasets/upload",
        files={"file": ("user_a.csv", _csv_bytes(), "text/csv")},
        headers={"X-Dataverse-User": user_a},
    )
    assert uploaded.status_code == 200

    sessions_a = client.get("/api/sessions", headers={"X-Dataverse-User": user_a}).json()
    sessions_b = client.get("/api/sessions", headers={"X-Dataverse-User": user_b}).json()
    datasets_a = client.get("/api/datasets", headers={"X-Dataverse-User": user_a}).json()
    datasets_b = client.get("/api/datasets", headers={"X-Dataverse-User": user_b}).json()

    assert [session["id"] for session in sessions_a] == [session_a]
    assert [session["id"] for session in sessions_b] == [session_b]
    assert [dataset["session_id"] for dataset in datasets_a] == [session_a]
    assert datasets_b == []


def test_food_dataset_upload_persists_semantic_type(tmp_path, monkeypatch):
    monkeypatch.setattr(session_service.supabase, "url", "")
    monkeypatch.setattr(session_service.supabase, "service_role_key", None)
    monkeypatch.setattr(session_service, "local", LocalPersistence(tmp_path / "chat_store"))

    client = TestClient(app)
    session_id = client.post("/api/sessions", json={"title": "New Chat"}).json()["session_id"]
    food_csv = (
        "food_name,food_description,main_ingredient,cuisine,spice_level,calories,category\n"
        "Pizza,cheesy flatbread,Cheese,Italian,Low,570,Fast Food\n"
        "Burger,grilled sandwich,Beef,American,Medium,650,Fast Food\n"
    ).encode("utf-8")

    uploaded = client.post(
        f"/api/sessions/{session_id}/datasets/upload",
        files={"file": ("food_dataset_extended.csv", food_csv, "text/csv")},
    )

    assert uploaded.status_code == 200
    dataset = uploaded.json()["dataset"]
    assert dataset["semantic_map"]["dataset_type"] == "food_dataset"
    assert dataset["schema_profile"]["dataset_type"] == "food_dataset"


def test_multiple_datasets_in_same_session_do_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(session_service.supabase, "url", "")
    monkeypatch.setattr(session_service.supabase, "service_role_key", None)
    monkeypatch.setattr(session_service, "local", LocalPersistence(tmp_path / "chat_store"))

    client = TestClient(app)
    session_id = client.post("/api/sessions", json={"title": "New Chat"}).json()["session_id"]
    first = client.post(
        f"/api/sessions/{session_id}/datasets/upload?auto_analyze=false",
        files={"file": ("first.csv", b"date,product,revenue\n2026-05-01,A,100\n", "text/csv")},
    ).json()
    second = client.post(
        f"/api/sessions/{session_id}/datasets/upload?auto_analyze=false",
        files={"file": ("second.csv", b"date,product,revenue\n2026-05-01,B,900\n2026-05-02,C,100\n", "text/csv")},
    ).json()

    first_analysis = client.post(
        f"/api/sessions/{session_id}/analyze",
        json={"dataset_id": first["dataset_id"], "user_prompt": "Summarize first", "run_xai": True, "generate_report": False},
    )
    second_analysis = client.post(
        f"/api/sessions/{session_id}/analyze",
        json={"dataset_id": second["dataset_id"], "user_prompt": "Summarize second", "run_xai": True, "generate_report": False},
    )

    assert first_analysis.status_code == 200
    assert second_analysis.status_code == 200
    assert first_analysis.json()["tables"][0]["rows"][0]["value"] == 1
    assert second_analysis.json()["tables"][0]["rows"][0]["value"] == 2


def test_storage_status_local_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(session_service.supabase, "url", "")
    monkeypatch.setattr(session_service.supabase, "service_role_key", None)
    monkeypatch.setattr(session_service, "local", LocalPersistence(tmp_path / "chat_store"))

    client = TestClient(app)
    response = client.get("/api/storage/status")
    assert response.status_code == 200
    assert response.json()["mode"] == "local"
    assert response.json()["supabase_configured"] is False
