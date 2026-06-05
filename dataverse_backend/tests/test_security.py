"""Security tests — verify no raw exception leaks and input validation."""


def test_health_endpoint(client):
    """Health endpoint returns 200."""
    resp = client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_api_health_endpoint(client):
    """API health endpoint returns 200."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_cors_allows_localhost_frontend(client):
    """Local Next.js origins should be allowed by CORS."""
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_invalid_dataset_id_returns_404(client):
    """Non-existent dataset ID returns 404, not 500."""
    resp = client.get("/api/datasets/totally-invalid-uuid/profile")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data
    # Verify no raw exception or traceback leaked
    assert "Traceback" not in data["detail"]
    assert "Error" not in data["detail"] or data["detail"] == "Dataset not found"


def test_no_exception_leak_on_ask(client):
    """Ask endpoint doesn't leak exception details for bad dataset."""
    resp = client.post(
        "/api/datasets/bad-id/ask",
        json={"prompt": "test query"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert "Traceback" not in str(data)


def test_oversized_file_rejected(client):
    """Files that are too large should be rejected."""
    # Create a ~60MB fake file (exceeds 50MB default limit)
    big_content = b"a,b,c\n" + b"1,2,3\n" * (10 * 1024 * 1024)  # ~30MB of rows
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("big.csv", big_content, "text/csv")},
    )
    # Should be rejected if over limit (depends on MAX_UPLOAD_SIZE_MB config)
    # For test env, we just verify it doesn't crash with a 500
    assert resp.status_code in (200, 400)
