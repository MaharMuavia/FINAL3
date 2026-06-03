"""Tests for dataset profile endpoint."""


def test_get_profile(client, uploaded_dataset_id):
    """Get profile for an uploaded dataset."""
    resp = client.get(f"/api/datasets/{uploaded_dataset_id}/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset_id"] == uploaded_dataset_id
    assert data["row_count"] == 20
    assert data["column_count"] == 6
    assert "Product" in data["columns"]


def test_profile_not_found(client):
    """Profile for non-existent dataset returns 404."""
    resp = client.get("/api/datasets/nonexistent-id/profile")
    assert resp.status_code == 404
