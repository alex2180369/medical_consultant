"""Routes for symptoms, complaints, and physician feedback."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from app.schemas import (
    ComplaintCreate,
    ComplaintRecord,
    ConsultationReceiptResponse,
    OpinionCompareRequest,
    ReceiptLineResponse,
)
from app.services.auth_service import AuthContext, get_auth_context
from app.services.billing_errors import http_error_for_insufficient_credits
from app.services.opinion_comparison_service import compare_opinions
from app.services.pii_filter import PII_WARNING, detect_sensitive_data
from app.services.receipt_service import ReceiptNotFoundError, get_complaint_receipt
from app.services.symptom_analyzer import analyze_complaint
from app.services.wallet_service import InsufficientCreditsError

router = APIRouter(prefix="/complaints", tags=["complaints"])


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


def _fetch_complaint(
    connection,
    complaint_id: int,
    user_id: str,
) -> ComplaintRecord:
    """Load a complaint by id."""
    row = connection.execute(
        "SELECT * FROM complaints WHERE id = %s AND user_id = %s",
        (complaint_id, user_id),
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Complaint not found.")

    return ComplaintRecord(**dict(row))


def _complaint_to_create(record: ComplaintRecord) -> ComplaintCreate:
    """Convert a stored complaint to an analysis payload."""
    return ComplaintCreate(
        symptoms=record.symptoms,
        doctor_feedback=record.doctor_feedback,
        notes=record.notes,
        occurred_at=record.occurred_at,
    )


def _save_analysis(
    connection,
    complaint_id: int,
    user_id: str,
    analysis,
) -> ComplaintRecord:
    """Persist AI analysis fields for a complaint."""
    connection.execute(
        """
        UPDATE complaints
        SET
            ai_analysis = %s,
            ai_diagnosis = %s,
            ai_treatment = %s,
            ai_doctor_questions = %s,
            ai_urgency = %s,
            ai_status = %s
        WHERE id = %s AND user_id = %s
        """,
        (
            analysis.ai_analysis,
            analysis.ai_diagnosis,
            analysis.ai_treatment,
            analysis.ai_doctor_questions,
            analysis.ai_urgency,
            analysis.ai_status,
            complaint_id,
            user_id,
        ),
    )
    return _fetch_complaint(connection, complaint_id, user_id)


@router.get("", response_model=list[ComplaintRecord])
def list_complaints(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[ComplaintRecord]:
    """Return complaint entries sorted by date."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM complaints
            WHERE user_id = %s
            ORDER BY occurred_at DESC, id DESC
            """,
            (auth.user_id,),
        ).fetchall()

    return [ComplaintRecord(**dict(row)) for row in rows]


@router.get("/{complaint_id}/receipt", response_model=ConsultationReceiptResponse)
def complaint_receipt(
    complaint_id: int,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> ConsultationReceiptResponse:
    """Return a usage receipt for the consultation linked to a complaint."""
    try:
        receipt = get_complaint_receipt(
            complaint_id=complaint_id,
            user_id=auth.user_id,
        )
    except ReceiptNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return _receipt_to_response(receipt)


@router.post("", response_model=ComplaintRecord, status_code=201)
def create_complaint(
    payload: ComplaintCreate,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> ComplaintRecord:
    """Store a complaint and run AI analysis for orientational guidance."""
    combined_text = " ".join(
        part
        for part in [payload.symptoms, payload.notes, payload.doctor_feedback]
        if part.strip()
    )
    if detect_sensitive_data(combined_text).contains_pii:
        raise HTTPException(status_code=400, detail=PII_WARNING)

    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO complaints (
                user_id,
                symptoms,
                doctor_feedback,
                notes,
                occurred_at
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                auth.user_id,
                payload.symptoms,
                payload.doctor_feedback,
                payload.notes,
                payload.occurred_at,
            ),
        ).fetchone()
        complaint_id = int(row["id"])

    try:
        analysis = analyze_complaint(
            payload,
            analysis_mode=payload.analysis_mode,
            user_id=auth.user_id,
        )
    except InsufficientCreditsError as error:
        raise http_error_for_insufficient_credits(error) from error

    with get_connection() as connection:
        return _save_analysis(
            connection,
            complaint_id,
            auth.user_id,
            analysis,
        )


@router.post("/{complaint_id}/compare-opinions", response_model=ComplaintRecord)
def compare_complaint_opinions(
    complaint_id: int,
    payload: OpinionCompareRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> ComplaintRecord:
    """Compare assistant first opinion with the doctor's in-person opinion."""
    try:
        updated, result = compare_opinions(
            complaint_id,
            payload.doctor_feedback,
            auth.user_id,
        )
    except InsufficientCreditsError as error:
        raise http_error_for_insufficient_credits(error) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if result.ai_status != "completed":
        raise HTTPException(
            status_code=502,
            detail=result.ai_opinion_comparison,
        )

    return updated


@router.post("/{complaint_id}/review", response_model=ComplaintRecord)
def review_complaint(
    complaint_id: int,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> ComplaintRecord:
    """Re-run analysis with the review model for a saved complaint."""
    with get_connection() as connection:
        record = _fetch_complaint(
            connection,
            complaint_id,
            auth.user_id,
        )

    try:
        analysis = analyze_complaint(
            _complaint_to_create(record),
            analysis_mode="review",
            user_id=auth.user_id,
        )
    except InsufficientCreditsError as error:
        raise http_error_for_insufficient_credits(error) from error

    with get_connection() as connection:
        return _save_analysis(
            connection,
            complaint_id,
            auth.user_id,
            analysis,
        )
