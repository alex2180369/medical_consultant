"""Tests for Appwrite-backed authentication."""

from fastapi.testclient import TestClient


def test_session_with_bearer_token(auth_client: TestClient) -> None:
    """Authenticated user should receive session info."""
    response = auth_client.get("/api/auth/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == "test-user"
    assert payload["user"]["email"] == "test@example.com"


def test_protected_route_requires_login(client: TestClient) -> None:
    """Medical routes should reject anonymous requests."""
    response = client.get("/api/profile")

    assert response.status_code == 401


def test_account_delete_requires_confirmation(auth_client: TestClient) -> None:
    """Account deletion should require explicit confirmation."""
    response = auth_client.request(
        "DELETE",
        "/api/account",
        json={"confirm": False},
    )

    assert response.status_code == 400
