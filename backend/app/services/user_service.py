"""User account persistence helpers."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.config import load_settings
from app.database import ensure_user_profile, get_connection

RESET_TOKEN_TTL = timedelta(minutes=30)
RESET_RATE_LIMIT = timedelta(minutes=5)

USER_SELECT_COLUMNS = """
    id,
    email,
    display_name,
    password_hash,
    status,
    role,
    ai_suggested_name,
    ai_email_analysis,
    ai_confidence,
    ai_analyzed_at,
    approved_at,
    approved_by,
    rejected_at,
    rejected_by,
    rejection_reason,
    created_at
"""


def _row_to_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "email": str(row["email"]),
        "display_name": str(row["display_name"]),
        "password_hash": str(row["password_hash"]),
        "status": str(row.get("status") or "pending"),
        "role": str(row.get("role") or "user"),
        "ai_suggested_name": str(row.get("ai_suggested_name") or ""),
        "ai_email_analysis": str(row.get("ai_email_analysis") or ""),
        "ai_confidence": str(row.get("ai_confidence") or ""),
        "ai_analyzed_at": row.get("ai_analyzed_at"),
        "approved_at": row.get("approved_at"),
        "approved_by": row.get("approved_by"),
        "rejected_at": row.get("rejected_at"),
        "rejected_by": row.get("rejected_by"),
        "rejection_reason": str(row.get("rejection_reason") or ""),
        "created_at": row.get("created_at"),
    }


def hash_reset_token(token: str) -> str:
    """Return a SHA-256 hash for a password reset token."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    """Normalize an email address for lookups and rate limits."""
    return email.strip().lower()


def is_email_blocked(email: str) -> bool:
    """Return True when registration is permanently blocked for an email."""
    normalized = normalize_email(email)
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM blocked_emails WHERE email = %s",
            (normalized,),
        ).fetchone()
    return row is not None


def block_email(*, email: str, reason: str, blocked_by: str) -> None:
    """Persist a permanently blocked email address."""
    normalized = normalize_email(email)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO blocked_emails (email, reason, blocked_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                reason = EXCLUDED.reason,
                blocked_at = NOW(),
                blocked_by = EXCLUDED.blocked_by
            """,
            (normalized, reason, blocked_by),
        )


def list_blocked_emails() -> list[dict[str, Any]]:
    """Return permanently blocked email addresses."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT email, reason, blocked_at, blocked_by
            FROM blocked_emails
            ORDER BY blocked_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    """Return a user row by primary key."""
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {USER_SELECT_COLUMNS}
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()

    return _row_to_user(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    """Return a user row by email address."""
    normalized = normalize_email(email)
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {USER_SELECT_COLUMNS}
            FROM users
            WHERE lower(email) = %s
            """,
            (normalized,),
        ).fetchone()

    return _row_to_user(row) if row else None


def list_users_by_status(status: str) -> list[dict[str, Any]]:
    """Return users filtered by moderation status."""
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {USER_SELECT_COLUMNS}
            FROM users
            WHERE status = %s
            ORDER BY created_at DESC
            """,
            (status,),
        ).fetchall()
    return [_row_to_user(row) for row in rows]


def _initial_user_status(email: str) -> str:
    settings = load_settings()
    if settings.app_env == "test":
        return "approved"
    admin_email = (settings.admin_email or "").strip().lower()
    if admin_email and normalize_email(email) == admin_email:
        return "approved"
    return "pending"


def _initial_user_role(email: str) -> str:
    settings = load_settings()
    admin_email = (settings.admin_email or "").strip().lower()
    if admin_email and normalize_email(email) == admin_email:
        return "admin"
    return "user"


def create_user(
    *,
    email: str,
    password_hash: str,
    display_name: str,
    consent_accepted_at: datetime,
) -> dict[str, Any]:
    """Create a pending registration application and an empty profile row."""
    normalized_email = normalize_email(email)

    if is_email_blocked(normalized_email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Регистрация с этим email невозможна.",
        )

    user_id = uuid.uuid4().hex
    user_status = _initial_user_status(normalized_email)
    user_role = _initial_user_role(normalized_email)

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT status FROM users WHERE lower(email) = %s",
            (normalized_email,),
        ).fetchone()
        if existing:
            existing_status = str(existing["status"])
            if existing_status == "pending":
                detail = "Заявка на регистрацию уже отправлена."
            elif existing_status == "rejected":
                detail = "Регистрация с этим email невозможна."
            else:
                detail = "Пользователь с таким email уже зарегистрирован."
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail,
            )

        connection.execute(
            """
            INSERT INTO users (
                id,
                email,
                password_hash,
                display_name,
                consent_accepted_at,
                status,
                role
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                normalized_email,
                password_hash,
                display_name.strip(),
                consent_accepted_at,
                user_status,
                user_role,
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

    if user_status == "approved":
        from app.services.wallet_service import grant_welcome_bonus

        grant_welcome_bonus(user_id)

    return user


def save_registration_enrichment(
    user_id: str,
    *,
    suggested_name: str,
    analysis: str,
    confidence: str,
) -> None:
    """Persist AI enrichment for a registration application."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET ai_suggested_name = %s,
                ai_email_analysis = %s,
                ai_confidence = %s,
                ai_analyzed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                suggested_name.strip(),
                analysis.strip(),
                confidence.strip(),
                user_id,
            ),
        )


def approve_user(*, user_id: str, admin_id: str) -> dict[str, Any]:
    """Approve a pending registration application."""
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден.",
        )
    if user["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Заявка уже обработана.",
        )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET status = 'approved',
                approved_at = NOW(),
                approved_by = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (admin_id, user_id),
        )

    updated = get_user_by_id(user_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить пользователя.",
        )

    from app.services.wallet_service import grant_welcome_bonus

    grant_welcome_bonus(user_id)
    return updated


def reject_user(
    *,
    user_id: str,
    admin_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Reject a pending registration application and block the email."""
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден.",
        )
    if user["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Заявка уже обработана.",
        )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET status = 'rejected',
                rejected_at = NOW(),
                rejected_by = %s,
                rejection_reason = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (admin_id, reason.strip(), user_id),
        )

    block_email(email=user["email"], reason="rejected", blocked_by=admin_id)

    updated = get_user_by_id(user_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить пользователя.",
        )
    return updated


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


def get_user_by_reset_token(plain_token: str) -> dict[str, Any] | None:
    """Return a user if the reset token is valid and not expired."""
    token_hash = hash_reset_token(plain_token)
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {USER_SELECT_COLUMNS}
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
