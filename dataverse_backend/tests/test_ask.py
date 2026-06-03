"""Tests for ask endpoint."""


def test_ask_top_products(client, uploaded_dataset_id):
    """Ask about highest selling product."""
    resp = client.post(
        f"/api/datasets/{uploaded_dataset_id}/ask",
        json={"prompt": "What is the highest selling product?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert len(data["answer"]) > 10  # Should have a substantive answer
    assert isinstance(data["tables"], list)
    assert isinstance(data["charts"], list)
    assert isinstance(data["recommendations"], list)


def test_ask_summary(client, uploaded_dataset_id):
    """Ask for a dataset summary."""
    resp = client.post(
        f"/api/datasets/{uploaded_dataset_id}/ask",
        json={"prompt": "Summarize this dataset"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert len(data["answer"]) > 10


def test_ask_quality(client, uploaded_dataset_id):
    """Ask about data quality."""
    resp = client.post(
        f"/api/datasets/{uploaded_dataset_id}/ask",
        json={"prompt": "Are there any data quality issues?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data


def test_ask_not_found(client):
    """Ask on non-existent dataset returns 404."""
    resp = client.post(
        "/api/datasets/nonexistent-id/ask",
        json={"prompt": "test"},
    )
    assert resp.status_code == 404


def test_ask_empty_prompt(client, uploaded_dataset_id):
    """Empty prompt should be rejected."""
    resp = client.post(
        f"/api/datasets/{uploaded_dataset_id}/ask",
        json={"prompt": ""},
    )
    assert resp.status_code == 422  # Pydantic validation error
