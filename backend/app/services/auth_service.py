"""Authentication helpers for family user accounts."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Response, status

from app.database import get_connection
from app.security import hash_password, verify_password

SESSION_COOKIE = "session_token"
SESSION_DURATION_DAYS = 30


@dataclass(frozen=True, slots=True)
class UserRecord:
    """Stored application user."""

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Authenticated request context with optional admin impersonation."""

    user: UserRecord
    effective_user_id: int


def _row_to_user(row) -> UserRecord:
    return UserRecord(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
    )


def get_user_by_id(user_id: int) -> UserRecord | None:
    """Load a user by id."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_user(row)


def get_user_by_username(username: str) -> UserRecord | None:
    """Load a user by username."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?",
            (username.strip().lower(),),
        ).fetchone()

    if row is None:
        return None

    return _row_to_user(row)


def _get_user_password_hash(username: str) -> str | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username.strip().lower(),),
        ).fetchone()

    if row is None:
        return None

    return str(row["password_hash"])


def list_active_users() -> list[UserRecord]:
    """Return all active users sorted by display name."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM users
            WHERE is_active = 1
            ORDER BY display_name ASC, username ASC
            """
        ).fetchall()

    return [_row_to_user(row) for row in rows]


def create_user(
    *,
    username: str,
    password: str,
    display_name: str,
    role: str = "member",
) -> UserRecord:
    """Create a new family user account."""
    normalized_username = username.strip().lower()
    cleaned_display_name = display_name.strip() or normalized_username

    if not normalized_username:
        raise ValueError("Имя пользователя не может быть пустым.")

    if len(password) < 4:
        raise ValueError("Пароль должен содержать минимум 4 символа.")

    password_hash = hash_password(password)

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM users WHERE username = ?",
            (normalized_username,),
        ).fetchone()
        if existing is not None:
            raise ValueError("Пользователь с таким именем уже существует.")

        cursor = connection.execute(
            """
            INSERT INTO users (username, password_hash, display_name, role, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (normalized_username, password_hash, cleaned_display_name, role),
        )
        user_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO profiles (user_id, full_name)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, cleaned_display_name),
        )
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError("Failed to create user.")

    return _row_to_user(row)


def authenticate_user(username: str, password: str) -> UserRecord | None:
    """Validate credentials and return the user if they match."""
    normalized_username = username.strip().lower()
    password_hash = _get_user_password_hash(normalized_username)
    if password_hash is None or not verify_password(password, password_hash):
        return None

    user = get_user_by_username(normalized_username)
    if user is None or not user.is_active:
        return None

    return user


def create_session(user_id: int) -> str:
    """Create a persisted session token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=SESSION_DURATION_DAYS)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO sessions (token, user_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (token, user_id, expires_at.isoformat()),
        )

    return token


def delete_session(token: str | None) -> None:
    """Remove a session token."""
    if not token:
        return

    with get_connection() as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))


def _load_session_user(token: str | None) -> UserRecord | None:
    if not token:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT users.*, sessions.expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()

    if row is None:
        return None

    if not bool(row["is_active"]):
        return None

    expires_at = datetime.fromisoformat(str(row["expires_at"]))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at < datetime.now(UTC):
        delete_session(token)
        return None

    return _row_to_user(row)


def set_session_cookie(response: Response, token: str) -> None:
    """Attach the session cookie to a response."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie from a response."""
    response.delete_cookie(key=SESSION_COOKIE, path="/")


def get_auth_context(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    x_act_as_user_id: Annotated[int | None, Header(alias="X-Act-As-User-Id")] = None,
) -> AuthContext:
    """Resolve the authenticated user and effective data scope."""
    user = _load_session_user(session_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход в систему.",
        )

    effective_user_id = user.id
    if x_act_as_user_id is not None and x_act_as_user_id != user.id:
        if user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выбора другого пользователя.",
            )

        target_user = get_user_by_id(x_act_as_user_id)
        if target_user is None or not target_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден.",
            )

        effective_user_id = target_user.id

    return AuthContext(user=user, effective_user_id=effective_user_id)


def require_admin(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContext:
    """Ensure the current user is an administrator."""
    if auth.user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для администратора.",
        )

    return auth
