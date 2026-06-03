"""Tests for dataset upload endpoint."""


def test_upload_valid_csv(client, sample_csv_bytes):
    """Upload a valid CSV and verify response structure."""
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("sales.csv", sample_csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "dataset_id" in data
    assert data["filename"] == "sales.csv"
    assert data["row_count"] == 20
    assert data["column_count"] == 6
    assert "Product" in data["columns"]
    assert "Revenue" in data["columns"]
    assert "profile" in data


def test_upload_rejects_invalid_type(client):
    """Reject non-CSV/XLSX files."""
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("data.json", b'{"key":"val"}', "application/json")},
    )
    assert resp.status_code == 400
    assert "CSV and Excel" in resp.json()["detail"]


def test_upload_rejects_empty_file(client):
    """Reject empty files."""
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()
