"""Smoke tests for the FastAPI backend."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    """Health endpoint should confirm the backend is available."""
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
