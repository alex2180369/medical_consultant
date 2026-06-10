"""Account management routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas import AccountDeleteRequest
from app.services.account_service import (
    delete_appwrite_user,
    hard_delete_user_data,
)
from app.services.auth_service import AuthContext, get_auth_context

router = APIRouter(prefix="/account", tags=["account"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: AccountDeleteRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    """Hard-delete all user data and the Appwrite account."""
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Подтвердите удаление аккаунта.",
        )

    hard_delete_user_data(auth.user_id)

    try:
        delete_appwrite_user(auth.user_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Данные удалены, но аккаунт Appwrite не удалён. Обратитесь в поддержку.",
        ) from error
