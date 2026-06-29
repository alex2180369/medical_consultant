"""Routes for multi-turn second-opinion consultations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.schemas import (
    ConsultationChatRequest,
    ConsultationChatResponse,
    ConsultationReceiptResponse,
    ReceiptLineResponse,
    TurnUsageInfo,
)
from app.services.auth_service import AuthContext, get_auth_context
from app.services.billing_errors import http_error_for_insufficient_credits
from app.services.consultation_service import continue_consultation
from app.services.receipt_service import ReceiptNotFoundError, get_consultation_receipt
from app.services.wallet_service import InsufficientCreditsError

router = APIRouter(prefix="/consultations", tags=["consultations"])


def _receipt_to_response(receipt) -> ConsultationReceiptResponse:
    return ConsultationReceiptResponse(
        consultation_id=receipt.consultation_id,
        occurred_at=receipt.occurred_at,
        status=receipt.status,
        complaint_id=receipt.complaint_id,
        total_tokens=receipt.total_tokens,
        total_estimated_credits=receipt.total_estimated_credits,
        total_charged_credits=receipt.total_charged_credits,
        free_turns_used=receipt.free_turns_used,
        lines=[
            ReceiptLineResponse(
                operation_type=line.operation_type,
                operation_label=line.operation_label,
                model=line.model,
                event_count=line.event_count,
                total_tokens=line.total_tokens,
                estimated_credits=line.estimated_credits,
                charged_credits=line.charged_credits,
            )
            for line in receipt.lines
        ],
        generated_at=receipt.generated_at,
    )


@router.get("/{consultation_id}/receipt", response_model=ConsultationReceiptResponse)
def consultation_receipt(
    consultation_id: int,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> ConsultationReceiptResponse:
    """Return a usage receipt for one consultation session."""
    try:
        receipt = get_consultation_receipt(
            consultation_id=consultation_id,
            user_id=auth.user_id,
        )
    except ReceiptNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return _receipt_to_response(receipt)


@router.post("/chat", response_model=ConsultationChatResponse)
def consultation_chat(
    payload: ConsultationChatRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> ConsultationChatResponse:
    """Continue a second-opinion consultation chat turn."""
    if payload.consultation_id is None and payload.occurred_at is None:
        raise HTTPException(
            status_code=422,
            detail="occurred_at is required when starting a new consultation.",
        )

    try:
        result = continue_consultation(
            message=payload.message,
            user_id=auth.user_id,
            consultation_id=payload.consultation_id,
            occurred_at=payload.occurred_at,
            doctor_feedback=payload.doctor_feedback,
            notes=payload.notes,
            force_complex=payload.force_complex,
        )
    except InsufficientCreditsError as error:
        raise http_error_for_insufficient_credits(error) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    usage = None
    if result.usage is not None:
        usage = TurnUsageInfo(
            credits_charged=result.usage.credits_charged,
            estimated_credits=result.usage.estimated_credits,
            tokens_total=result.usage.tokens_total,
            model=result.usage.model,
            balance_remaining=result.usage.balance_remaining,
            free_turns_remaining=result.usage.free_turns_remaining,
            used_free_turn=result.usage.used_free_turn,
        )

    return ConsultationChatResponse(
        consultation_id=result.consultation_id,
        reply=result.reply,
        phase=result.phase,
        ai_status=result.ai_status,
        complaint=result.complaint,
        usage=usage,
    )
