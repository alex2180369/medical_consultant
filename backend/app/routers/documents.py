"""Routes for storing medical documents locally."""

import uuid
from pathlib import Path
from shutil import copyfileobj
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.config import load_settings
from app.database import get_connection
from app.schemas import DocumentRecord
from app.services.auth_service import AuthContext, get_auth_context
from app.services.document_analyzer import extract_document_text

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = load_settings().uploads_dir


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


@router.post("", response_model=DocumentRecord, status_code=201)
def upload_document(
    file: Annotated[UploadFile, File()],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    description: Annotated[str, Form()] = "",
) -> DocumentRecord:
    """Store a PDF, text file, scan, or image and extract text for the assistant."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original_name = Path(file.filename or "document").name
    destination = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{original_name}"

    with destination.open("wb") as output:
        copyfileobj(file.file, output)

    extraction = extract_document_text(
        destination,
        content_type=file.content_type or "",
        description=description,
    )

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
