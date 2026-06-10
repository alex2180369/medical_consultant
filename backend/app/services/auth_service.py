"""Appwrite JWT authentication helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, status

from app.config import load_settings
from app.database import ensure_user_profile


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Authenticated request context."""

    user_id: str
    email: str
    name: str


def _verify_appwrite_jwt(jwt: str) -> dict[str, str]:
    """Validate an Appwrite JWT and return the account payload."""
    settings = load_settings()
    if not settings.appwrite_project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Appwrite не настроен на сервере.",
        )

    try:
        response = httpx.get(
            f"{settings.appwrite_endpoint.rstrip('/')}/account",
            headers={
                "X-Appwrite-Project": settings.appwrite_project_id,
                "X-Appwrite-JWT": jwt,
            },
            timeout=15,
        )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось проверить сессию Appwrite.",
        ) from error

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия недействительна. Войдите снова.",
        )

    payload = response.json()
    user_id = str(payload.get("$id", "")).strip()
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


def get_auth_context(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    """Resolve the authenticated Appwrite user from a Bearer JWT."""
    settings = load_settings()

    if settings.app_env == "test":
        if authorization == "Bearer test-user":
            ensure_user_profile("test-user", email="test@example.com", display_name="Test")
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

    jwt = authorization.removeprefix("Bearer ").strip()
    if not jwt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход в систему.",
        )

    account = _verify_appwrite_jwt(jwt)
    ensure_user_profile(
        account["user_id"],
        email=account["email"],
        display_name=account["name"],
    )

    return AuthContext(
        user_id=account["user_id"],
        email=account["email"],
        name=account["name"],
    )
