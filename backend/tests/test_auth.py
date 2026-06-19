"""Tests for email/password authentication."""

import uuid

from fastapi.testclient import TestClient


def test_register_and_login(client: TestClient) -> None:
    """User can register and then log in after approval."""
    email = f"auth-test-{uuid.uuid4().hex[:8]}@example.com"
    register_response = client.post(
        "/api/auth/register",
        json={
            "name": "Auth Test",
            "email": email,
            "password": "Secret123!",
            "consent": True,
        },
    )
    assert register_response.status_code == 201
    register_payload = register_response.json()
    assert "message" in register_payload
    assert "access_token" not in register_payload

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "Secret123!",
        },
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"]


def test_login_with_wrong_password(client: TestClient) -> None:
    """Invalid credentials should be rejected."""
    email = f"wrong-pass-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={
            "name": "Wrong Pass",
            "email": email,
            "password": "Secret123!",
            "consent": True,
        },
    )

    response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": "bad-password",
        },
    )

    assert response.status_code == 401


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
