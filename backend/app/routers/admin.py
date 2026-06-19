"""Administrative moderation routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas import (
    AdminUserRecord,
    BlockedEmailRecord,
    MessageResponse,
    RejectUserRequest,
)
from app.services.admin_service import disable_and_delete_user
from app.services.auth_service import AuthContext, get_auth_context, require_admin
from app.services.user_service import (
    approve_user,
    get_user_by_id,
    list_blocked_emails,
    list_users_by_status,
    reject_user,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_admin_record(user: dict[str, object]) -> AdminUserRecord:
    return AdminUserRecord(
        id=str(user["id"]),
        email=str(user["email"]),
        name=str(user["display_name"]),
        status=str(user["status"]),
        role=str(user["role"]),
        ai_suggested_name=str(user.get("ai_suggested_name") or ""),
        ai_email_analysis=str(user.get("ai_email_analysis") or ""),
        ai_confidence=str(user.get("ai_confidence") or ""),
        ai_analyzed_at=user.get("ai_analyzed_at"),  # type: ignore[arg-type]
        approved_at=user.get("approved_at"),  # type: ignore[arg-type]
        rejected_at=user.get("rejected_at"),  # type: ignore[arg-type]
        rejection_reason=str(user.get("rejection_reason") or ""),
        created_at=user.get("created_at"),  # type: ignore[arg-type]
    )


@router.get("/applications", response_model=list[AdminUserRecord])
def list_applications(
    admin: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[AdminUserRecord]:
    """Return pending registration applications."""
    require_admin(admin)
    return [_to_admin_record(user) for user in list_users_by_status("pending")]


@router.get("/users", response_model=list[AdminUserRecord])
def list_users(
    admin: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[AdminUserRecord]:
    """Return approved users."""
    require_admin(admin)
    return [_to_admin_record(user) for user in list_users_by_status("approved")]


@router.get("/blocked-emails", response_model=list[BlockedEmailRecord])
def list_blocked(
    admin: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[BlockedEmailRecord]:
    """Return permanently blocked email addresses."""
    require_admin(admin)
    return [
        BlockedEmailRecord(
            email=str(item["email"]),
            reason=str(item["reason"]),
            blocked_at=item["blocked_at"],  # type: ignore[arg-type]
            blocked_by=str(item.get("blocked_by") or ""),
        )
        for item in list_blocked_emails()
    ]


@router.get("/users/{user_id}", response_model=AdminUserRecord)
def get_user(
    user_id: str,
    admin: Annotated[AuthContext, Depends(get_auth_context)],
) -> AdminUserRecord:
    """Return a single user record for moderation."""
    require_admin(admin)
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден.",
        )
    return _to_admin_record(user)


@router.post("/users/{user_id}/approve", response_model=AdminUserRecord)
def approve_application(
    user_id: str,
    admin: Annotated[AuthContext, Depends(get_auth_context)],
) -> AdminUserRecord:
    """Approve a pending registration application."""
    require_admin(admin)
    user = approve_user(user_id=user_id, admin_id=admin.user_id)
    return _to_admin_record(user)


@router.post("/users/{user_id}/reject", response_model=AdminUserRecord)
def reject_application(
    user_id: str,
    payload: RejectUserRequest,
    admin: Annotated[AuthContext, Depends(get_auth_context)],
) -> AdminUserRecord:
    """Reject a pending registration application."""
    require_admin(admin)
    user = reject_user(
        user_id=user_id,
        admin_id=admin.user_id,
        reason=payload.reason,
    )
    return _to_admin_record(user)


@router.delete("/users/{user_id}", response_model=MessageResponse)
def disable_user(
    user_id: str,
    admin: Annotated[AuthContext, Depends(get_auth_context)],
) -> MessageResponse:
    """Delete an approved user and block their email permanently."""
    require_admin(admin)
    try:
        disable_and_delete_user(user_id=user_id, admin_id=admin.user_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    return MessageResponse(message="Пользователь отключён и удалён.")
