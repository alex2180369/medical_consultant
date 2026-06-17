"""JWT authentication helpers."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import load_settings
from app.database import ensure_user_profile
from app.services.user_service import get_user_by_id


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Authenticated request context."""

    user_id: str
    email: str
    name: str


def hash_password(password: str) -> str:
    """Return a bcrypt hash for a plaintext password."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check whether a plaintext password matches the stored hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(*, user_id: str, email: str, name: str) -> str:
    """Issue a signed JWT for an authenticated user."""
    settings = load_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "exp": expires_at,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, str]:
    """Validate a JWT and return its claims."""
    settings = load_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия недействительна. Войдите снова.",
        ) from error

    user_id = str(payload.get("sub", "")).strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не удалось определить пользователя.",
        )

    return {
        "user_id": user_id,
        "email": str(payload.get("email", "")),
        "name": str(payload.get("name", "")),
    }


def generate_reset_token() -> str:
    """Create a URL-safe password reset token."""
    return secrets.token_urlsafe(32)


def get_auth_context(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    """Resolve the authenticated user from a Bearer JWT."""
    settings = load_settings()

    if settings.app_env == "test":
        if authorization == "Bearer test-user":
            ensure_user_profile(
                "test-user",
                email="test@example.com",
                display_name="Test",
            )
            return AuthContext(
                user_id="test-user",
                email="test@example.com",
                name="Test User",
            )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход в систему.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход в систему.",
        )

    if settings.app_env == "test" and token == "test-user":
        ensure_user_profile(
            "test-user",
            email="test@example.com",
            display_name="Test",
        )
        return AuthContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
        )

    claims = decode_access_token(token)
    user = get_user_by_id(claims["user_id"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия недействительна. Войдите снова.",
        )

    return AuthContext(
        user_id=user["id"],
        email=user["email"],
        name=user["display_name"],
    )
