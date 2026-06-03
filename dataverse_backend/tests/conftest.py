"""Test fixtures and shared configuration for DataVerse AI tests."""
from __future__ import annotations

import io
import os
import tempfile

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Set test env before importing app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_dataverse.db"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="dataverse_test_")
os.environ["ENVIRONMENT"] = "test"

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    """Synchronous test client for FastAPI."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_csv_bytes() -> bytes:
    """Generate a simple sales CSV for testing."""
    df = pd.DataFrame({
        "Product": ["Widget A", "Widget B", "Gadget X", "Gadget Y", "Widget A",
                     "Widget B", "Gadget X", "Gadget Y", "Widget A", "Widget B",
                     "Gadget X", "Gadget Y", "Widget A", "Widget B", "Gadget X",
                     "Gadget Y", "Widget A", "Widget B", "Gadget X", "Gadget Y"],
        "Category": ["Widgets", "Widgets", "Gadgets", "Gadgets", "Widgets",
                      "Widgets", "Gadgets", "Gadgets", "Widgets", "Widgets",
                      "Gadgets", "Gadgets", "Widgets", "Widgets", "Gadgets",
                      "Gadgets", "Widgets", "Widgets", "Gadgets", "Gadgets"],
        "Revenue": [100, 200, 150, 80, 120, 210, 160, 90, 130, 220,
                    170, 85, 140, 230, 180, 95, 150, 240, 190, 100],
        "Quantity": [10, 20, 15, 8, 12, 21, 16, 9, 13, 22,
                     17, 8, 14, 23, 18, 9, 15, 24, 19, 10],
        "Date": pd.date_range("2024-01-01", periods=20, freq="W").strftime("%Y-%m-%d").tolist(),
        "Region": ["North", "South", "East", "West", "North",
                    "South", "East", "West", "North", "South",
                    "East", "West", "North", "South", "East",
                    "West", "North", "South", "East", "West"],
    })
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def uploaded_dataset_id(client, sample_csv_bytes) -> str:
    """Upload a dataset and return its ID."""
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("test_data.csv", sample_csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()["dataset_id"]
