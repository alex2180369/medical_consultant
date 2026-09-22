"""Pre-flight credit estimates for document uploads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, load_settings
from app.services.document_analyzer import (
    IMAGE_EXTENSIONS,
    PDF_EXTENSIONS,
    TEXT_EXTENSIONS,
)
from app.services.llm_router import LlmTask, resolve_model_route
from app.services.pricing import calculate_usage_cost, calculate_yandex_ocr_cost
from app.services.yandex_ocr import is_yandex_ocr_configured

HEAVY_ESTIMATE_CREDITS = 12
HEAVY_IMAGE_BYTES = 2 * 1024 * 1024
HEAVY_PDF_PAGES = 5
OCR_COMPLETION_TOKENS = 700
OCR_BASE_PROMPT_TOKENS = 400


@dataclass(frozen=True, slots=True)
class DocumentCostEstimate:
    """Estimated billing impact before processing a document."""

    estimated_credits: int
    requires_confirmation: bool
    is_billable: bool
    analysis_type: str
    warning_message: str | None
    page_count: int | None
    file_size_bytes: int
    model: str | None = None


def _estimate_llm_ocr_credits(
    settings: Settings, *, prompt_tokens: int
) -> tuple[int, str]:
    route = resolve_model_route(LlmTask.IMAGING, settings)
    _, credits = calculate_usage_cost(
        model=route.model,
        task=LlmTask.IMAGING,
        prompt_tokens=prompt_tokens,
        completion_tokens=OCR_COMPLETION_TOKENS,
    )
    return credits, route.model


def _estimate_yandex_ocr_credits(
    settings: Settings,
    *,
    page_count: int,
) -> tuple[int, str]:
    _, credits = calculate_yandex_ocr_cost(
        page_count=page_count,
        credits_per_page=settings.yandex_ocr_credits_per_page,
    )
    return credits, "yandex-vision-ocr"


def _estimate_ocr_credits(
    settings: Settings,
    *,
    page_count: int,
    prompt_tokens: int,
) -> tuple[int, str]:
    if is_yandex_ocr_configured(settings):
        return _estimate_yandex_ocr_credits(settings, page_count=page_count)
    return _estimate_llm_ocr_credits(settings, prompt_tokens=prompt_tokens)


def _pdf_page_count(path: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError:
        return 1

    reader = PdfReader(str(path))
    return max(len(reader.pages), 1)


def _pdf_has_extractable_text(path: Path) -> bool:
    try:
        from pypdf import PdfReader
    except ImportError:
        return False

    reader = PdfReader(str(path))
    for page in reader.pages[:3]:
        if (page.extract_text() or "").strip():
            return True
    return False


def estimate_document_cost(
    path: Path,
    *,
    content_type: str = "",
    settings: Settings | None = None,
) -> DocumentCostEstimate:
    """Estimate credits for a document before OCR or extraction."""
    settings = settings or load_settings()
    suffix = path.suffix.lower()
    file_size = path.stat().st_size

    if suffix in TEXT_EXTENSIONS:
        return DocumentCostEstimate(
            estimated_credits=0,
            requires_confirmation=False,
            is_billable=False,
            analysis_type="text",
            warning_message=None,
            page_count=None,
            file_size_bytes=file_size,
        )

    if suffix in PDF_EXTENSIONS:
        pages = min(_pdf_page_count(path), 10)
        if _pdf_has_extractable_text(path):
            return DocumentCostEstimate(
                estimated_credits=0,
                requires_confirmation=False,
                is_billable=False,
                analysis_type="pdf_text",
                warning_message=None,
                page_count=pages,
                file_size_bytes=file_size,
            )

        prompt_tokens = OCR_BASE_PROMPT_TOKENS + pages * 350
        credits, model = _estimate_ocr_credits(
            settings,
            page_count=pages,
            prompt_tokens=prompt_tokens,
        )
        requires_confirmation = (
            credits >= HEAVY_ESTIMATE_CREDITS or pages >= HEAVY_PDF_PAGES
        )
        warning = None
        if requires_confirmation:
            warning = (
                f"PDF похож на скан ({pages} стр.). "
                f"OCR может стоить около {credits} 💎."
            )
        return DocumentCostEstimate(
            estimated_credits=credits,
            requires_confirmation=requires_confirmation,
            is_billable=True,
            analysis_type="pdf_scan",
            warning_message=warning,
            page_count=pages,
            file_size_bytes=file_size,
            model=model,
        )

    if suffix in IMAGE_EXTENSIONS:
        prompt_tokens = OCR_BASE_PROMPT_TOKENS + max(file_size // 900, 1)
        credits, model = _estimate_ocr_credits(
            settings,
            page_count=1,
            prompt_tokens=prompt_tokens,
        )
        requires_confirmation = (
            credits >= HEAVY_ESTIMATE_CREDITS or file_size >= HEAVY_IMAGE_BYTES
        )
        warning = None
        if requires_confirmation:
            warning = (
                f"Файл содержит много данных "
                f"({round(file_size / (1024 * 1024), 1)} МБ). "
                f"OCR может стоить около {credits} 💎."
            )
        return DocumentCostEstimate(
            estimated_credits=credits,
            requires_confirmation=requires_confirmation,
            is_billable=True,
            analysis_type="ocr",
            warning_message=warning,
            page_count=1,
            file_size_bytes=file_size,
            model=model,
        )

    return DocumentCostEstimate(
        estimated_credits=0,
        requires_confirmation=False,
        is_billable=False,
        analysis_type="unsupported",
        warning_message="Формат файла пока не поддерживается.",
        page_count=None,
        file_size_bytes=file_size,
    )
