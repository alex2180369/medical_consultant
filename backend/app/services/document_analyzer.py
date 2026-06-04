"""Extract text from uploaded medical documents for consultation context."""

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, load_settings
from app.database import get_connection
from app.services.llm_client import ChatMessage, chat_completion
from app.services.llm_router import LlmTask

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_EXTENSIONS = {".txt"}
PDF_EXTENSIONS = {".pdf"}
MAX_STORED_TEXT = 8000
MAX_CONTEXT_CHARS = 1500
RECENT_DOCUMENTS_LIMIT = 3

OCR_PROMPT = """
Извлеки текст с медицинского документа или снимка.
Верни только распознанный текст и ключевые показатели без комментариев.
Если текст неразборчив, кратко опиши, что видно на изображении.
Пиши на русском.
""".strip()


@dataclass(frozen=True, slots=True)
class DocumentExtractionResult:
    """Result of local or OCR text extraction."""

    extracted_text: str
    analysis_status: str


def _truncate(text: str, limit: int) -> str:
    """Trim text to a safe length for storage or prompts."""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _read_text_file(path: Path) -> str:
    """Read a plain-text document."""
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf_text(path: Path) -> str:
    """Extract text from a PDF when possible."""
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("PDF support requires the pypdf package.") from error

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages[:10]:
        page_text = page.extract_text() or ""
        if page_text.strip():
            parts.append(page_text.strip())

    return "\n\n".join(parts)


def _image_mime_type(path: Path, content_type: str) -> str:
    """Resolve MIME type for an image upload."""
    if content_type.startswith("image/"):
        return content_type

    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "image/jpeg"


def _ocr_image(path: Path, content_type: str, settings: Settings) -> str:
    """Run OCR on an image through the imaging model."""
    if not settings.proxyapi_api_key:
        raise RuntimeError("PROXYAPI_API_KEY is not configured.")

    mime_type = _image_mime_type(path, content_type)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"

    completion = chat_completion(
        settings,
        LlmTask.IMAGING,
        messages=[
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": OCR_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            )
        ],
        temperature=0.1,
        timeout=180.0,
    )
    return completion.content.strip()


def extract_document_text(
    path: Path,
    *,
    content_type: str = "",
    description: str = "",
    settings: Settings | None = None,
) -> DocumentExtractionResult:
    """Extract readable text from an uploaded document."""
    settings = settings or load_settings()
    suffix = path.suffix.lower()
    description = description.strip()

    try:
        if suffix in TEXT_EXTENSIONS:
            extracted = _read_text_file(path)
            status = "completed" if extracted.strip() else "failed"
        elif suffix in PDF_EXTENSIONS:
            extracted = _read_pdf_text(path)
            if not extracted.strip():
                extracted = (
                    "Текст из PDF не извлечён автоматически. "
                    "Если это скан, загрузите фото или JPG/PNG."
                )
                status = "failed"
            else:
                status = "completed"
        elif suffix in IMAGE_EXTENSIONS:
            extracted = _ocr_image(path, content_type, settings)
            status = "completed" if extracted.strip() else "failed"
        else:
            extracted = description or "Формат файла пока не поддерживается."
            return DocumentExtractionResult(
                extracted_text=_truncate(extracted, MAX_STORED_TEXT),
                analysis_status="unsupported",
            )
    except RuntimeError as error:
        message = str(error)
        if "PROXYAPI_API_KEY" in message and description:
            extracted = f"{description}\n\n(OCR недоступен без PROXYAPI_API_KEY.)"
        else:
            extracted = description or message
        return DocumentExtractionResult(
            extracted_text=_truncate(extracted, MAX_STORED_TEXT),
            analysis_status="no_api_key" if "API key" in message else "failed",
        )
    except Exception as error:
        fallback = description or f"Не удалось разобрать файл: {error}"
        return DocumentExtractionResult(
            extracted_text=_truncate(fallback, MAX_STORED_TEXT),
            analysis_status="failed",
        )

    if description and extracted.strip():
        extracted = f"{description}\n\n{extracted.strip()}"
    elif description:
        extracted = description

    return DocumentExtractionResult(
        extracted_text=_truncate(extracted, MAX_STORED_TEXT),
        analysis_status=status,
    )


def load_recent_documents(
    user_id: int,
    limit: int = RECENT_DOCUMENTS_LIMIT,
) -> list[dict[str, str]]:
    """Load recent documents with extracted text."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT filename, description, extracted_text, analysis_status, created_at
            FROM documents
            WHERE user_id = ? AND TRIM(extracted_text) != ''
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def format_documents_for_context(
    user_id: int,
    documents: list[dict[str, str]] | None = None,
) -> str:
    """Format uploaded documents for LLM context."""
    documents = documents if documents is not None else load_recent_documents(user_id)
    if not documents:
        return "Нет загруженных документов."

    blocks: list[str] = []
    for item in documents:
        filename = item.get("filename", "файл")
        description = item.get("description", "").strip()
        extracted = _truncate(item.get("extracted_text", ""), MAX_CONTEXT_CHARS)
        status = item.get("analysis_status", "")
        header = f"Файл: {filename}"
        if description:
            header += f" ({description})"
        if status and status != "completed":
            header += f" [статус: {status}]"
        blocks.append(f"{header}\n{extracted}")

    return "\n\n---\n\n".join(blocks)
