"""Appwrite-backed session routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas import SessionInfo, UserPublic
from app.services.auth_service import AuthContext, get_auth_context

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_public(auth: AuthContext) -> UserPublic:
    return UserPublic(
        id=auth.user_id,
        email=auth.email,
        name=auth.name,
    )


@router.get("/me", response_model=SessionInfo)
def current_session(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> SessionInfo:
    """Return the authenticated Appwrite user."""
    return SessionInfo(user=_to_public(auth))
