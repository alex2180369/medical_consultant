"""Account management routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas import (
    AccountDeleteRequest,
    UsageEventResponse,
    UsageSummaryResponse,
    WalletResponse,
    WalletTransactionResponse,
)
from app.services.account_service import hard_delete_user_data
from app.services.auth_service import AuthContext, get_auth_context
from app.services.pricing import CREDITS_PER_RUB
from app.services.usage_service import get_user_usage_summary, list_user_usage_events
from app.services.wallet_service import (
    STARTER_CREDITS,
    get_wallet_balance,
    list_wallet_transactions,
)

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/wallet", response_model=WalletResponse)
def get_wallet(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> WalletResponse:
    """Return the current wallet balance for the authenticated user."""
    wallet = get_wallet_balance(auth.user_id)
    return WalletResponse(
        credits_balance=wallet.credits_balance,
        free_turns_remaining=wallet.free_turns_remaining,
        credits_per_rub=CREDITS_PER_RUB,
        starter_credits=STARTER_CREDITS,
    )


@router.get("/wallet/transactions", response_model=list[WalletTransactionResponse])
def get_wallet_transactions(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[WalletTransactionResponse]:
    """Return recent wallet transactions."""
    rows = list_wallet_transactions(auth.user_id, limit=limit)
    return [
        WalletTransactionResponse(
            id=int(row["id"]),
            delta_credits=int(row["delta_credits"]),
            reason=str(row["reason"]),
            reference_id=row.get("reference_id"),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.get("/usage/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> UsageSummaryResponse:
    """Return aggregated LLM usage for the current account."""
    summary = get_user_usage_summary(auth.user_id)
    return UsageSummaryResponse(
        total_events=summary.total_events,
        total_tokens=summary.total_tokens,
        total_estimated_credits=summary.total_estimated_credits,
        total_charged_credits=summary.total_charged_credits,
        credits_per_rub=summary.credits_per_rub,
        by_operation=summary.by_operation,
    )


@router.get("/usage/events", response_model=list[UsageEventResponse])
def get_usage_events(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[UsageEventResponse]:
    """Return recent LLM usage events for the current account."""
    events = list_user_usage_events(auth.user_id, limit=limit)
    return [
        UsageEventResponse(
            id=event.id,
            operation_type=event.operation_type,
            llm_task=event.llm_task,
            provider=event.provider,
            model=event.model,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            total_tokens=event.total_tokens,
            estimated_credits=event.estimated_credits,
            charged_credits=event.charged_credits,
            cache_hit=event.cache_hit,
            is_charged=event.is_charged,
            consultation_id=event.consultation_id,
            complaint_id=event.complaint_id,
            document_id=event.document_id,
            created_at=event.created_at,
        )
        for event in events
    ]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: AccountDeleteRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    """Hard-delete all user data and the account."""
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Подтвердите удаление аккаунта.",
        )

    hard_delete_user_data(auth.user_id)
