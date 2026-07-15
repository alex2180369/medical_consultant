"""Routes for storing medical documents locally."""

import uuid
from pathlib import Path
from shutil import copyfileobj
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.config import load_settings
from app.database import get_connection
from app.schemas import DocumentCostEstimateResponse, DocumentRecord
from app.services.auth_service import AuthContext, get_auth_context
from app.services.billing_errors import http_error_for_insufficient_credits
from app.services.document_analyzer import extract_document_text
from app.services.document_cost_estimator import estimate_document_cost
from app.services.wallet_service import InsufficientCreditsError

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = load_settings().uploads_dir


def _estimate_to_response(estimate) -> DocumentCostEstimateResponse:
    return DocumentCostEstimateResponse(
        estimated_credits=estimate.estimated_credits,
        requires_confirmation=estimate.requires_confirmation,
        is_billable=estimate.is_billable,
        analysis_type=estimate.analysis_type,
        warning_message=estimate.warning_message,
        page_count=estimate.page_count,
        file_size_bytes=estimate.file_size_bytes,
        model=estimate.model,
    )


@router.get("", response_model=list[DocumentRecord])
def list_documents(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[DocumentRecord]:
    """Return uploaded document metadata."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM documents
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (auth.user_id,),
        ).fetchall()

    return [DocumentRecord(**dict(row)) for row in rows]


@router.post("/estimate", response_model=DocumentCostEstimateResponse)
def estimate_document_upload(
    file: Annotated[UploadFile, File()],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> DocumentCostEstimateResponse:
    """Estimate credits for a document before OCR or extraction."""
    del auth
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original_name = Path(file.filename or "document").name
    destination = UPLOAD_DIR / f"estimate_{uuid.uuid4().hex[:8]}_{original_name}"

    try:
        with destination.open("wb") as output:
            copyfileobj(file.file, output)
        estimate = estimate_document_cost(
            destination,
            content_type=file.content_type or "",
        )
        return _estimate_to_response(estimate)
    finally:
        destination.unlink(missing_ok=True)


@router.post("", response_model=DocumentRecord, status_code=201)
def upload_document(
    file: Annotated[UploadFile, File()],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    description: Annotated[str, Form()] = "",
    confirm_high_cost: Annotated[bool, Form()] = False,
) -> DocumentRecord:
    """Store a PDF, text file, scan, or image and extract text for the assistant."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original_name = Path(file.filename or "document").name
    destination = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{original_name}"

    with destination.open("wb") as output:
        copyfileobj(file.file, output)

    estimate = estimate_document_cost(
        destination,
        content_type=file.content_type or "",
    )
    if estimate.requires_confirmation and not confirm_high_cost:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "message": estimate.warning_message
                or "Для загрузки этого файла нужно подтверждение.",
                "estimate": _estimate_to_response(estimate).model_dump(),
            },
        )

    try:
        extraction = extract_document_text(
            destination,
            content_type=file.content_type or "",
            description=description,
            user_id=auth.user_id,
        )
    except InsufficientCreditsError as error:
        destination.unlink(missing_ok=True)
        raise http_error_for_insufficient_credits(error) from error

    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO documents (
                user_id,
                filename,
                content_type,
                path,
                description,
                extracted_text,
                analysis_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                auth.user_id,
                original_name,
                file.content_type or "",
                str(destination),
                description,
                extraction.extracted_text,
                extraction.analysis_status,
            ),
        ).fetchone()
        document_id = int(row["id"])
        row = connection.execute(
            "SELECT * FROM documents WHERE id = %s AND user_id = %s",
            (document_id, auth.user_id),
        ).fetchone()

    return DocumentRecord(**dict(row))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    """Delete an uploaded document owned by the current user."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, path
            FROM documents
            WHERE id = %s AND user_id = %s
            """,
            (document_id, auth.user_id),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Документ не найден.",
            )

        file_path = Path(str(row["path"]))
        connection.execute(
            "DELETE FROM documents WHERE id = %s AND user_id = %s",
            (document_id, auth.user_id),
        )

    if file_path.exists() and UPLOAD_DIR.resolve() in file_path.resolve().parents:
        file_path.unlink(missing_ok=True)
