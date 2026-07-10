"""Tests for Yandex Vision OCR client helpers."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.services.yandex_ocr import (
    YandexOcrError,
    _extract_full_text,
    is_yandex_ocr_configured,
    recognize_document,
)
from tests.test_settings import make_test_settings


def test_is_yandex_ocr_configured() -> None:
    assert is_yandex_ocr_configured(make_test_settings()) is False
    assert (
        is_yandex_ocr_configured(make_test_settings(yandex_ocr_api_key="secret"))
        is True
    )


def test_extract_full_text_from_sync_payload() -> None:
    payload = {
        "result": {
            "textAnnotation": {
                "fullText": "Гемоглобин 145 г/л\nЛейкоциты 6.2",
                "pages": [{"width": 100, "height": 200}],
            }
        }
    }
    text, pages = _extract_full_text(payload)
    assert "Гемоглобин 145" in text
    assert pages == 1


def test_recognize_document_sync(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "scan.jpg"
    path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 64)
    settings = make_test_settings(yandex_ocr_api_key="test-key")

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {
                "result": {
                    "textAnnotation": {
                        "fullText": "Глюкоза 5.4 ммоль/л",
                        "pages": [{}],
                    }
                }
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url: str, headers=None, json=None) -> FakeResponse:
            assert "recognizeText" in url
            assert "Async" not in url
            assert headers["Authorization"] == "Api-Key test-key"
            assert json["mimeType"] == "JPEG"
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)

    result = recognize_document(path, settings)
    assert "Глюкоза 5.4" in result.text
    assert result.page_count == 1
    assert result.provider == "yandex.cloud"


def test_recognize_document_requires_api_key(tmp_path: Path) -> None:
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    with pytest.raises(YandexOcrError, match="YANDEX_OCR_API_KEY"):
        recognize_document(path, make_test_settings())


def test_estimate_uses_yandex_pricing_when_configured(tmp_path: Path) -> None:
    from app.services.document_cost_estimator import estimate_document_cost

    path = tmp_path / "scan.jpg"
    path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 2048)

    estimate = estimate_document_cost(
        path,
        settings=make_test_settings(
            yandex_ocr_api_key="key",
            yandex_ocr_credits_per_page=2,
        ),
    )
    assert estimate.model == "yandex-vision-ocr"
    assert estimate.estimated_credits == 2
    assert estimate.is_billable is True


def test_extract_prefers_yandex_over_llm(monkeypatch, tmp_path: Path) -> None:
    from app.services import document_analyzer as analyzer

    path = tmp_path / "lab.jpg"
    path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 32)

    class FakeResult:
        text = "СОЭ 12 мм/ч\nГемоглобин 145 г/л\nЛейкоциты 6.2"
        page_count = 1
        provider = "yandex.cloud"
        model = "yandex-vision-ocr"

    monkeypatch.setattr(
        analyzer,
        "recognize_document",
        lambda *_args, **_kwargs: FakeResult(),
    )
    monkeypatch.setattr(analyzer, "prepare_billable_request", lambda *_a, **_k: None)
    monkeypatch.setattr(analyzer, "log_ocr_usage", lambda **_k: None)

    called = {"llm": False}

    def fake_llm(*_a, **_k):
        called["llm"] = True
        return "should-not-run"

    monkeypatch.setattr(analyzer, "_ocr_image_llm", fake_llm)

    result = analyzer.extract_document_text(
        path,
        content_type="image/jpeg",
        settings=make_test_settings(yandex_ocr_api_key="key"),
        user_id="u1",
    )
    assert result.analysis_status == "completed"
    assert "СОЭ 12" in result.extracted_text
    assert called["llm"] is False
