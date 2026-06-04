"""Routes for storing medical documents locally."""

import uuid
from pathlib import Path
from shutil import copyfileobj
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.database import get_connection
from app.schemas import DocumentRecord
from app.services.auth_service import AuthContext, get_auth_context
from app.services.document_analyzer import extract_document_text

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = Path("./data/uploads")


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
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (auth.effective_user_id,),
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
        cursor = connection.execute(
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
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                auth.effective_user_id,
                original_name,
                file.content_type or "",
                str(destination),
                description,
                extraction.extracted_text,
                extraction.analysis_status,
            ),
        )
        document_id = int(cursor.lastrowid)
        row = connection.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?",
            (document_id, auth.effective_user_id),
        ).fetchone()

    return DocumentRecord(**dict(row))
