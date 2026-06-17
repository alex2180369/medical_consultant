"""User account persistence helpers."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.database import ensure_user_profile, get_connection

RESET_TOKEN_TTL = timedelta(minutes=30)
RESET_RATE_LIMIT = timedelta(minutes=5)


def _row_to_user(row: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(row["id"]),
        "email": str(row["email"]),
        "display_name": str(row["display_name"]),
        "password_hash": str(row["password_hash"]),
    }


def hash_reset_token(token: str) -> str:
    """Return a SHA-256 hash for a password reset token."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    """Normalize an email address for lookups and rate limits."""
    return email.strip().lower()


def get_user_by_id(user_id: str) -> dict[str, str] | None:
    """Return a user row by primary key."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, email, display_name, password_hash
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()

    return _row_to_user(row) if row else None


def get_user_by_email(email: str) -> dict[str, str] | None:
    """Return a user row by email address."""
    normalized = normalize_email(email)
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, email, display_name, password_hash
            FROM users
            WHERE lower(email) = %s
            """,
            (normalized,),
        ).fetchone()

    return _row_to_user(row) if row else None


def create_user(
    *,
    email: str,
    password_hash: str,
    display_name: str,
    consent_accepted_at: datetime,
) -> dict[str, str]:
    """Create a user and an empty profile row."""
    user_id = uuid.uuid4().hex
    normalized_email = email.strip().lower()

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT 1 FROM users WHERE lower(email) = %s",
            (normalized_email,),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Пользователь с таким email уже зарегистрирован.",
            )

        connection.execute(
            """
            INSERT INTO users (
                id,
                email,
                password_hash,
                display_name,
                consent_accepted_at
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user_id,
                normalized_email,
                password_hash,
                display_name.strip(),
                consent_accepted_at,
            ),
        )

    ensure_user_profile(
        user_id,
        email=normalized_email,
        display_name=display_name.strip(),
        consent_accepted_at=consent_accepted_at,
    )

    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать пользователя.",
        )
    return user


def update_user_password(user_id: str, password_hash: str) -> None:
    """Replace the stored password hash."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET password_hash = %s,
                password_reset_token = NULL,
                password_reset_expires_at = NULL,
                updated_at = NOW()
            WHERE id = %s
            """,
            (password_hash, user_id),
        )


def set_password_reset_token(user_id: str, plain_token: str, expires_at: datetime) -> None:
    """Persist a hashed password reset token for a user."""
    token_hash = hash_reset_token(plain_token)
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET password_reset_token = %s,
                password_reset_expires_at = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (token_hash, expires_at, user_id),
        )


def get_user_by_reset_token(plain_token: str) -> dict[str, str] | None:
    """Return a user if the reset token is valid and not expired."""
    token_hash = hash_reset_token(plain_token)
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, email, display_name, password_hash
            FROM users
            WHERE password_reset_token = %s
              AND password_reset_expires_at IS NOT NULL
              AND password_reset_expires_at > %s
            """,
            (token_hash, datetime.now(UTC)),
        ).fetchone()

    return _row_to_user(row) if row else None


def clear_password_reset_token(user_id: str) -> None:
    """Invalidate an active password reset token."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET password_reset_token = NULL,
                password_reset_expires_at = NULL,
                updated_at = NOW()
            WHERE id = %s
            """,
            (user_id,),
        )


def is_password_reset_rate_limited(email: str) -> bool:
    """Return True if a reset email was requested too recently."""
    normalized = normalize_email(email)
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT last_requested_at
            FROM password_reset_rate_limits
            WHERE email = %s
            """,
            (normalized,),
        ).fetchone()

    if row is None:
        return False

    last_requested_at = row["last_requested_at"]
    if last_requested_at.tzinfo is None:
        last_requested_at = last_requested_at.replace(tzinfo=UTC)

    return datetime.now(UTC) - last_requested_at < RESET_RATE_LIMIT


def record_password_reset_request(email: str) -> None:
    """Store the timestamp of a password reset request."""
    normalized = normalize_email(email)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO password_reset_rate_limits (email, last_requested_at)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET
                last_requested_at = EXCLUDED.last_requested_at
            """,
            (normalized, datetime.now(UTC)),
        )


def delete_user(user_id: str) -> None:
    """Remove the user row after profile data has been deleted."""
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM users WHERE id = %s",
            (user_id,),
        )
