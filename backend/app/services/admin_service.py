"""Admin moderation actions."""

from __future__ import annotations

from app.services.account_service import hard_delete_user_data
from app.services.user_service import (
    approve_user,
    block_email,
    get_user_by_id,
    reject_user,
)


def disable_and_delete_user(*, user_id: str, admin_id: str) -> None:
    """Delete an approved user and permanently block their email."""
    user = get_user_by_id(user_id)
    if user is None:
        raise ValueError("Пользователь не найден.")

    if user["status"] != "approved":
        raise ValueError("Можно отключить только одобренного пользователя.")

    if user["role"] == "admin":
        raise ValueError("Нельзя отключить администратора.")

    block_email(email=user["email"], reason="disabled", blocked_by=admin_id)
    hard_delete_user_data(user_id)
