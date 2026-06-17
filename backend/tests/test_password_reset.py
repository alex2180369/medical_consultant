"""Tests for password reset security."""

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import get_connection
from app.services.user_service import hash_reset_token


def _register(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Reset Test",
            "email": email,
            "password": "Secret123!",
            "consent": True,
        },
    )
    assert response.status_code == 201


@patch("app.routers.auth.send_password_reset_email")
@patch("app.routers.auth.smtp_configured", return_value=True)
def test_reset_token_is_hashed_in_database(
    _smtp_configured: object,
    mock_send: object,
    client: TestClient,
) -> None:
    """Reset tokens must be stored as SHA-256 hashes."""
    email = f"hash-{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)

    client.post("/api/auth/forgot-password", json={"email": email})

    reset_url = mock_send.call_args.kwargs["reset_url"]
    plain_token = reset_url.split("reset=")[-1]

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT password_reset_token
            FROM users
            WHERE lower(email) = %s
            """,
            (email.lower(),),
        ).fetchone()

    assert row is not None
    assert row["password_reset_token"] == hash_reset_token(plain_token)
    assert row["password_reset_token"] != plain_token


@patch("app.routers.auth.send_password_reset_email")
@patch("app.routers.auth.smtp_configured", return_value=True)
def test_reset_token_is_single_use(
    _smtp_configured: object,
    mock_send: object,
    client: TestClient,
) -> None:
    """A reset token must become invalid after password change."""
    email = f"single-{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)

    client.post("/api/auth/forgot-password", json={"email": email})
    plain_token = mock_send.call_args.kwargs["reset_url"].split("reset=")[-1]

    first_reset = client.post(
        "/api/auth/reset-password",
        json={"token": plain_token, "password": "NewSecret123!"},
    )
    assert first_reset.status_code == 200

    second_reset = client.post(
        "/api/auth/reset-password",
        json={"token": plain_token, "password": "Another123!"},
    )
    assert second_reset.status_code == 400


@patch("app.routers.auth.send_password_reset_email")
@patch("app.routers.auth.smtp_configured", return_value=True)
def test_forgot_password_rate_limit(
    _smtp_configured: object,
    mock_send: object,
    client: TestClient,
) -> None:
    """Only one reset email per address should be sent within five minutes."""
    email = f"rate-{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)

    first = client.post("/api/auth/forgot-password", json={"email": email})
    second = client.post("/api/auth/forgot-password", json={"email": email})

    assert first.status_code == 200
    assert second.status_code == 200
    assert mock_send.call_count == 1
