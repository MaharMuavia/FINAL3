"""Tests for dataset delete endpoint."""


def test_delete_dataset(client, uploaded_dataset_id):
    """Delete an uploaded dataset."""
    resp = client.delete(f"/api/datasets/{uploaded_dataset_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True

    # Verify it's gone
    resp2 = client.get(f"/api/datasets/{uploaded_dataset_id}/profile")
    assert resp2.status_code == 404


def test_delete_not_found(client):
    """Delete non-existent dataset returns 404."""
    resp = client.delete("/api/datasets/nonexistent-id")
    assert resp.status_code == 404
