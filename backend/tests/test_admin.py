"""Tests for admin moderation workflow."""

import os
import uuid

from fastapi.testclient import TestClient

ADMIN_EMAIL = "admin@example.com"
os.environ["ADMIN_EMAIL"] = ADMIN_EMAIL


def _register_pending(client: TestClient, *, email: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Pending User",
            "email": email,
            "password": "Secret123!",
            "consent": True,
        },
    )
    assert response.status_code == 201


def _login(client: TestClient, *, email: str, password: str = "Secret123!") -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_pending_user_cannot_login(client: TestClient, monkeypatch) -> None:
    """Pending users should be blocked at login in production mode."""
    monkeypatch.setenv("APP_ENV", "production")
    email = f"pending-{uuid.uuid4().hex[:8]}@example.com"

    _register_pending(client, email=email)

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "Secret123!"},
    )

    assert response.status_code == 403
    assert "рассмотрении" in response.json()["detail"]


def test_admin_can_approve_and_user_can_login(client: TestClient, monkeypatch) -> None:
    """Admin should approve a pending application."""
    monkeypatch.setenv("APP_ENV", "production")

    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    user_email = f"approve-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setenv("ADMIN_EMAIL", admin_email)

    client.post(
        "/api/auth/register",
        json={
            "name": "Admin",
            "email": admin_email,
            "password": "Secret123!",
            "consent": True,
        },
    )
    _register_pending(client, email=user_email)

    admin_token = _login(client, email=admin_email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    apps_response = client.get("/api/admin/applications", headers=admin_headers)
    assert apps_response.status_code == 200
    applications = apps_response.json()
    assert len(applications) >= 1
    pending_user = next(item for item in applications if item["email"] == user_email)

    approve_response = client.post(
        f"/api/admin/users/{pending_user['id']}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    login_response = client.post(
        "/api/auth/login",
        json={"email": user_email, "password": "Secret123!"},
    )
    assert login_response.status_code == 200


def test_admin_can_reject_and_block_email(client: TestClient, monkeypatch) -> None:
    """Rejected users and their email should stay blocked."""
    monkeypatch.setenv("APP_ENV", "production")

    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    user_email = f"reject-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setenv("ADMIN_EMAIL", admin_email)

    client.post(
        "/api/auth/register",
        json={
            "name": "Admin",
            "email": admin_email,
            "password": "Secret123!",
            "consent": True,
        },
    )
    _register_pending(client, email=user_email)

    admin_token = _login(client, email=admin_email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    apps_response = client.get("/api/admin/applications", headers=admin_headers)
    pending_user = next(
        item for item in apps_response.json() if item["email"] == user_email
    )

    reject_response = client.post(
        f"/api/admin/users/{pending_user['id']}/reject",
        headers=admin_headers,
        json={"reason": "Тестовая причина"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    login_response = client.post(
        "/api/auth/login",
        json={"email": user_email, "password": "Secret123!"},
    )
    assert login_response.status_code == 403

    re_register_response = client.post(
        "/api/auth/register",
        json={
            "name": "Blocked User",
            "email": user_email,
            "password": "Secret123!",
            "consent": True,
        },
    )
    assert re_register_response.status_code == 403


def test_non_admin_cannot_access_admin_routes(client: TestClient) -> None:
    """Regular users should not access admin endpoints."""
    email = f"regular-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={
            "name": "Regular",
            "email": email,
            "password": "Secret123!",
            "consent": True,
        },
    )
    token = _login(client, email=email)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/admin/applications", headers=headers)

    assert response.status_code == 403
