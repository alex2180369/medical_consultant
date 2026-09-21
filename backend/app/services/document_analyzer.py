"""Extract text from uploaded medical documents for consultation context."""

from __future__ import annotations

import base64
import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, load_settings
from app.database import get_connection
from app.services.llm_client import ChatMessage, chat_completion
from app.services.llm_router import LlmTask
from app.services.usage_service import (
    UsageContext,
    log_ocr_usage,
    prepare_billable_request,
)
from app.services.yandex_ocr import (
    MIN_USEFUL_TEXT_CHARS,
    YandexOcrError,
    is_yandex_ocr_configured,
    recognize_document,
)

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_EXTENSIONS = {".txt"}
PDF_EXTENSIONS = {".pdf"}
MAX_STORED_TEXT = 8000
MAX_CONTEXT_CHARS = 1500
RECENT_DOCUMENTS_LIMIT = 3

_MAGIC_PREFIXES: dict[str, bytes] = {
    ".pdf": b"%PDF-",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".webp": b"RIFF",
}


def validate_uploaded_file(
    path: Path,
    *,
    settings: Settings | None = None,
    max_bytes: int | None = None,
) -> None:
    """Reject unsupported extensions and mismatched file contents.

    Raises ValueError with a user-safe message when a file must not be accepted.
    """
    settings = settings or load_settings()
    suffix = path.suffix.lower()
    size = path.stat().st_size

    if suffix not in IMAGE_EXTENSIONS | PDF_EXTENSIONS | TEXT_EXTENSIONS:
        raise ValueError(
            "Поддерживаются только изображения (JPG, PNG, WEBP), "
            "PDF и текстовые файлы."
        )

    limit = max_bytes if max_bytes is not None else settings.max_upload_bytes
    if size > limit:
        raise ValueError(
            f"Файл слишком большой (лимит {round(limit / (1024 * 1024), 1)} МБ)."
        )

    if suffix in TEXT_EXTENSIONS:
        return

    with path.open("rb") as handle:
        header = handle.read(32)

    if suffix == ".webp":
        if not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
            raise ValueError("Файл не похож на изображение WEBP.")
        return

    expected = _MAGIC_PREFIXES[suffix]
    if not header.startswith(expected):
        kind = "PDF" if suffix in PDF_EXTENSIONS else "изображение"
        raise ValueError(f"Файл не похож на {kind}.")

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


def _ocr_with_yandex(
    path: Path,
    settings: Settings,
    *,
    user_id: str | None = None,
    document_id: int | None = None,
) -> str:
    """Run Yandex Vision OCR and bill by page count."""
    context = UsageContext(
        user_id=user_id,
        operation_type="ocr",
        document_id=document_id,
        task=LlmTask.IMAGING,
    )
    prepare_billable_request(context)
    result = recognize_document(path, settings)
    log_ocr_usage(
        context=context,
        provider=result.provider,
        model=result.model,
        page_count=max(result.page_count, 1),
        credits_per_page=settings.yandex_ocr_credits_per_page,
    )
    return result.text.strip()


def _ocr_image_llm(
    path: Path,
    content_type: str,
    settings: Settings,
    *,
    user_id: str | None = None,
    document_id: int | None = None,
) -> str:
    """Run OCR on an image through the imaging model (fallback)."""
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
        usage_context=UsageContext(
            user_id=user_id,
            operation_type="ocr",
            document_id=document_id,
            task=LlmTask.IMAGING,
        ),
    )
    return completion.content.strip()


def _ocr_document(
    path: Path,
    content_type: str,
    settings: Settings,
    *,
    user_id: str | None = None,
    document_id: int | None = None,
    allow_llm_fallback: bool = True,
) -> str:
    """Prefer Yandex Vision OCR; optionally fall back to vision LLM for images."""
    yandex_error: Exception | None = None

    if is_yandex_ocr_configured(settings):
        try:
            text = _ocr_with_yandex(
                path,
                settings,
                user_id=user_id,
                document_id=document_id,
            )
            if len(text) >= MIN_USEFUL_TEXT_CHARS:
                return text
            logger.info(
                "Yandex OCR returned weak text (%s chars) for %s",
                len(text),
                path.name,
            )
            if text and not allow_llm_fallback:
                return text
        except YandexOcrError as error:
            yandex_error = error
            logger.warning("Yandex OCR failed for %s: %s", path.name, error)

    suffix = path.suffix.lower()
    if allow_llm_fallback and suffix in IMAGE_EXTENSIONS:
        try:
            return _ocr_image_llm(
                path,
                content_type,
                settings,
                user_id=user_id,
                document_id=document_id,
            )
        except RuntimeError:
            if yandex_error is not None:
                raise yandex_error from None
            raise

    if yandex_error is not None:
        raise yandex_error

    if not is_yandex_ocr_configured(settings) and not settings.proxyapi_api_key:
        raise RuntimeError(
            "OCR is not configured. Set YANDEX_OCR_API_KEY or PROXYAPI_API_KEY."
        )

    raise RuntimeError("OCR did not return usable text.")


def extract_document_text(
    path: Path,
    *,
    content_type: str = "",
    description: str = "",
    settings: Settings | None = None,
    user_id: str | None = None,
    document_id: int | None = None,
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
            if extracted.strip():
                status = "completed"
            else:
                # Scanned PDF: try Yandex OCR (supports PDF natively).
                try:
                    extracted = _ocr_document(
                        path,
                        content_type or "application/pdf",
                        settings,
                        user_id=user_id,
                        document_id=document_id,
                        allow_llm_fallback=False,
                    )
                    status = "completed" if extracted.strip() else "failed"
                except RuntimeError as error:
                    message = str(error)
                    if "not configured" in message.lower() or "API_KEY" in message:
                        extracted = (
                            "Текст из PDF не извлечён автоматически. "
                            "Для сканов настройте YANDEX_OCR_API_KEY "
                            "или загрузите фото JPG/PNG."
                        )
                        status = "no_api_key"
                    else:
                        extracted = (
                            "Текст из PDF не извлечён автоматически. "
                            "Если это скан, загрузите фото или JPG/PNG."
                        )
                        status = "failed"
        elif suffix in IMAGE_EXTENSIONS:
            extracted = _ocr_document(
                path,
                content_type,
                settings,
                user_id=user_id,
                document_id=document_id,
                allow_llm_fallback=True,
            )
            status = "completed" if extracted.strip() else "failed"
        else:
            extracted = description or "Формат файла пока не поддерживается."
            return DocumentExtractionResult(
                extracted_text=_truncate(extracted, MAX_STORED_TEXT),
                analysis_status="unsupported",
            )
    except RuntimeError as error:
        logger.exception("Failed to extract text from file %s", path.name)
        message = str(error)
        missing_key = (
            "API_KEY" in message
            or "not configured" in message.lower()
            or "YANDEX_OCR" in message
        )
        if missing_key and description:
            extracted = (
                f"{description}\n\n"
                "(OCR недоступен: задайте YANDEX_OCR_API_KEY или PROXYAPI_API_KEY.)"
            )
        else:
            extracted = (
                description
                or "Не удалось распознать файл. Загрузите документ ещё раз."
            )
        return DocumentExtractionResult(
            extracted_text=_truncate(extracted, MAX_STORED_TEXT),
            analysis_status="no_api_key" if missing_key else "failed",
        )
    except Exception:
        logger.exception(
            "Failed to extract text from file %s (status likely failed)",
            path.name,
        )
        if description:
            extracted = (
                f"{description}\n\n"
                "(OCR недоступен: задайте YANDEX_OCR_API_KEY или PROXYAPI_API_KEY.)"
            )
            analysis_status = "no_api_key"
        else:
            extracted = "Не удалось распознать файл. Загрузите документ ещё раз."
            analysis_status = "failed"
        return DocumentExtractionResult(
            extracted_text=_truncate(extracted, MAX_STORED_TEXT),
            analysis_status=analysis_status,
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
    user_id: str,
    limit: int = RECENT_DOCUMENTS_LIMIT,
) -> list[dict[str, str]]:
    """Load recent documents with extracted text."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT filename, description, extracted_text, analysis_status, created_at
            FROM documents
            WHERE user_id = %s AND TRIM(extracted_text) != ''
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def format_documents_for_context(
    user_id: str,
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
