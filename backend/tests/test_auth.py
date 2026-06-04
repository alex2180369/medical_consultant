"""Tests for family user authentication."""

import uuid

from fastapi.testclient import TestClient

from app.main import app


def test_login_with_admin_credentials(auth_client: TestClient) -> None:
    """Admin should receive a session."""
    response = auth_client.get("/api/auth/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["username"] == "admin"
    assert payload["is_admin"] is True


def test_protected_route_requires_login(client: TestClient) -> None:
    """Medical routes should reject anonymous requests."""
    response = client.get("/api/profile")

    assert response.status_code == 401


def test_admin_can_list_users(auth_client: TestClient) -> None:
    """Admin should see the family user list."""
    response = auth_client.get("/api/auth/users")

    assert response.status_code == 200
    payload = response.json()
    assert any(user["username"] == "admin" for user in payload)


def test_admin_can_create_family_user(auth_client: TestClient) -> None:
    """Admin should be able to create another account."""
    username = f"maria_{uuid.uuid4().hex[:8]}"
    response = auth_client.post(
        "/api/auth/users",
        json={
            "username": username,
            "password": "secret",
            "display_name": "Мария",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["username"] == username
    assert payload["display_name"] == "Мария"


def test_admin_can_act_as_family_user(auth_client: TestClient) -> None:
    """Admin should access another user's profile via header."""
    username = f"pavel_{uuid.uuid4().hex[:8]}"
    create_response = auth_client.post(
        "/api/auth/users",
        json={
            "username": username,
            "password": "secret",
            "display_name": "Павел",
        },
    )
    user_id = create_response.json()["id"]

    profile_response = auth_client.put(
        "/api/profile",
        headers={"X-Act-As-User-Id": str(user_id)},
        json={"full_name": "Павел", "sex": "мужской"},
    )

    assert profile_response.status_code == 200
    assert profile_response.json()["full_name"] == "Павел"

    scoped_response = auth_client.get(
        "/api/profile",
        headers={"X-Act-As-User-Id": str(user_id)},
    )
    assert scoped_response.json()["full_name"] == "Павел"

    admin_response = auth_client.get("/api/profile")
    assert admin_response.json()["full_name"] != "Павел"


def test_family_user_cannot_impersonate(auth_client: TestClient) -> None:
    """Regular users must not switch to another account."""
    username = f"anna_{uuid.uuid4().hex[:8]}"
    auth_client.post(
        "/api/auth/users",
        json={
            "username": username,
            "password": "secret",
            "display_name": "Анна",
        },
    )

    with TestClient(app) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "secret"},
        )
        assert login_response.status_code == 200

        response = client.get(
            "/api/profile",
            headers={"X-Act-As-User-Id": "1"},
        )

    assert response.status_code == 403
