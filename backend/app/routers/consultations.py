"""Routes for multi-turn second-opinion consultations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.schemas import ConsultationChatRequest, ConsultationChatResponse
from app.services.auth_service import AuthContext, get_auth_context
from app.services.consultation_service import continue_consultation

router = APIRouter(prefix="/consultations", tags=["consultations"])


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
            user_id=auth.effective_user_id,
            consultation_id=payload.consultation_id,
            occurred_at=payload.occurred_at,
            doctor_feedback=payload.doctor_feedback,
            notes=payload.notes,
            force_complex=payload.force_complex,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return ConsultationChatResponse(
        consultation_id=result.consultation_id,
        reply=result.reply,
        phase=result.phase,
        ai_status=result.ai_status,
        complaint=result.complaint,
    )
