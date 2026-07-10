"""Yandex Vision OCR client for medical document text extraction."""

from __future__ import annotations

import base64
import logging
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

SYNC_ENDPOINT = "/recognizeText"
ASYNC_ENDPOINT = "/recognizeTextAsync"
GET_RECOGNITION_ENDPOINT = "/getRecognition"
OPERATIONS_BASE_URL = "https://operation.api.cloud.yandex.net/operations"

SUPPORTED_IMAGE_MIME = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "JPEG",
}
PDF_MIME = "PDF"
MIN_USEFUL_TEXT_CHARS = 20
ASYNC_POLL_INTERVAL_SEC = 1.5
ASYNC_MAX_WAIT_SEC = 90.0


class YandexOcrError(RuntimeError):
    """Raised when Yandex Vision OCR fails."""


@dataclass(frozen=True, slots=True)
class YandexOcrResult:
    """Normalized OCR output from Yandex Vision."""

    text: str
    page_count: int
    provider: str = "yandex.cloud"
    model: str = "yandex-vision-ocr"


def is_yandex_ocr_configured(settings: Settings) -> bool:
    """Return True when Yandex OCR credentials are present."""
    return bool(settings.yandex_ocr_api_key and settings.yandex_ocr_api_key.strip())


def _resolve_mime_type(path: Path) -> str:
    """Map file extension to Yandex OCR mimeType enum."""
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_IMAGE_MIME:
        return SUPPORTED_IMAGE_MIME[suffix]
    if suffix == ".pdf":
        return PDF_MIME

    guessed, _ = mimetypes.guess_type(path.name)
    if guessed == "image/jpeg":
        return "JPEG"
    if guessed == "image/png":
        return "PNG"
    if guessed == "application/pdf":
        return PDF_MIME
    raise YandexOcrError(f"Unsupported file type for Yandex OCR: {suffix or path.name}")


def _auth_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Authorization": f"Api-Key {settings.yandex_ocr_api_key}",
        "Content-Type": "application/json",
    }
    folder_id = (settings.yandex_ocr_folder_id or "").strip()
    if folder_id:
        headers["x-folder-id"] = folder_id
    return headers


def _base_url(settings: Settings) -> str:
    return settings.yandex_ocr_base_url.rstrip("/")


def _request_body(content_b64: str, mime_type: str) -> dict[str, object]:
    return {
        "mimeType": mime_type,
        "languageCodes": ["ru", "en"],
        "model": "page",
        "content": content_b64,
    }


def _extract_full_text(payload: object) -> tuple[str, int]:
    """Pull fullText / page count from sync or getRecognition payloads."""
    texts: list[str] = []
    pages = 0

    def walk(node: object) -> None:
        nonlocal pages
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        annotation = node.get("textAnnotation")
        if isinstance(annotation, dict):
            full_text = annotation.get("fullText") or annotation.get("full_text")
            if isinstance(full_text, str) and full_text.strip():
                texts.append(full_text.strip())
            page_list = annotation.get("pages")
            if isinstance(page_list, list) and page_list:
                pages = max(pages, len(page_list))

        page = node.get("page")
        if isinstance(page, int):
            pages = max(pages, page + 1)

        result = node.get("result")
        if result is not None:
            walk(result)
        results = node.get("results")
        if results is not None:
            walk(results)

    walk(payload)
    combined = "\n\n".join(texts).strip()
    if pages <= 0:
        pages = 1 if combined else 0
    return combined, pages


def _recognize_sync(
    settings: Settings,
    *,
    content_b64: str,
    mime_type: str,
    timeout: float = 60.0,
) -> YandexOcrResult:
    url = f"{_base_url(settings)}{SYNC_ENDPOINT}"
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            headers=_auth_headers(settings),
            json=_request_body(content_b64, mime_type),
        )

    if response.status_code >= 400:
        raise YandexOcrError(
            f"Yandex OCR sync failed ({response.status_code}): {response.text[:300]}"
        )

    text, pages = _extract_full_text(response.json())
    return YandexOcrResult(text=text, page_count=max(pages, 1 if text else 0))


def _wait_operation(settings: Settings, operation_id: str) -> dict[str, object]:
    url = f"{OPERATIONS_BASE_URL}/{operation_id}"
    deadline = time.monotonic() + ASYNC_MAX_WAIT_SEC
    with httpx.Client(timeout=30.0) as client:
        while time.monotonic() < deadline:
            response = client.get(url, headers=_auth_headers(settings))
            if response.status_code >= 400:
                raise YandexOcrError(
                    f"Yandex OCR operation poll failed ({response.status_code}): "
                    f"{response.text[:300]}"
                )
            payload = response.json()
            if payload.get("done") is True:
                if payload.get("error"):
                    raise YandexOcrError(f"Yandex OCR operation error: {payload['error']}")
                return payload
            time.sleep(ASYNC_POLL_INTERVAL_SEC)

    raise YandexOcrError("Yandex OCR async recognition timed out.")


def _get_recognition(settings: Settings, operation_id: str) -> YandexOcrResult:
    url = f"{_base_url(settings)}{GET_RECOGNITION_ENDPOINT}"
    with httpx.Client(timeout=60.0) as client:
        response = client.get(
            url,
            headers=_auth_headers(settings),
            params={"operationId": operation_id},
        )

    if response.status_code >= 400:
        # Some API revisions stream JSON lines; fall back to raw text parse.
        raise YandexOcrError(
            f"Yandex OCR getRecognition failed ({response.status_code}): "
            f"{response.text[:300]}"
        )

    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        payload: object = response.json()
    else:
        # NDJSON / concatenated JSON objects
        chunks: list[object] = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                import json

                chunks.append(json.loads(line))
            except Exception:
                continue
        payload = chunks if chunks else response.text

    text, pages = _extract_full_text(payload)
    if not text and isinstance(payload, dict):
        # Operation response may embed recognition under response/result.
        nested = payload.get("response") or payload.get("result")
        if nested is not None:
            text, pages = _extract_full_text(nested)

    return YandexOcrResult(text=text, page_count=max(pages, 1 if text else 0))


def _recognize_async(
    settings: Settings,
    *,
    content_b64: str,
    mime_type: str,
) -> YandexOcrResult:
    url = f"{_base_url(settings)}{ASYNC_ENDPOINT}"
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            url,
            headers=_auth_headers(settings),
            json=_request_body(content_b64, mime_type),
        )

    if response.status_code >= 400:
        raise YandexOcrError(
            f"Yandex OCR async failed ({response.status_code}): {response.text[:300]}"
        )

    payload = response.json()
    operation_id = payload.get("id")
    if not isinstance(operation_id, str) or not operation_id:
        raise YandexOcrError("Yandex OCR async response missing operation id.")

    operation = _wait_operation(settings, operation_id)
    # Prefer dedicated getRecognition; fall back to operation.response.
    try:
        result = _get_recognition(settings, operation_id)
        if result.text.strip():
            return result
    except YandexOcrError as error:
        logger.warning("getRecognition failed, using operation payload: %s", error)

    text, pages = _extract_full_text(operation.get("response") or operation)
    return YandexOcrResult(text=text, page_count=max(pages, 1 if text else 0))


def recognize_document(path: Path, settings: Settings) -> YandexOcrResult:
    """Recognize text from an image or PDF via Yandex Vision OCR."""
    if not is_yandex_ocr_configured(settings):
        raise YandexOcrError("YANDEX_OCR_API_KEY is not configured.")

    mime_type = _resolve_mime_type(path)
    content_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

    if mime_type == PDF_MIME:
        return _recognize_async(
            settings,
            content_b64=content_b64,
            mime_type=mime_type,
        )

    return _recognize_sync(
        settings,
        content_b64=content_b64,
        mime_type=mime_type,
    )


__all__ = [
    "MIN_USEFUL_TEXT_CHARS",
    "YandexOcrError",
    "YandexOcrResult",
    "is_yandex_ocr_configured",
    "recognize_document",
]
