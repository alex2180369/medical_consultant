"""Tests for document upload and consultation context."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services.document_analyzer import (
    extract_document_text,
    format_documents_for_context,
)


def _settings() -> Settings:
    """Build test settings without external API keys."""
    return Settings(
        app_env="test",
        app_name="test",
        database_path=Path(":memory:"),
        aitunnel_api_key=None,
        proxyapi_api_key=None,
        symptoms_model="symptoms-model",
        medications_model="medications-model",
        complex_symptoms_model="complex-model",
        review_model="review-model",
        imaging_model="imaging-model",
        aitunnel_base_url="https://api.aitunnel.ru/v1",
        proxyapi_base_url="https://api.proxyapi.ru/openai/v1",
    )


def test_extract_text_file() -> None:
    """Plain text files should be readable without an API key."""
    path = Path("tests/fixtures/sample_lab.txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Гемоглобин 145 г/л", encoding="utf-8")

    result = extract_document_text(
        path,
        description="ОАК",
        settings=_settings(),
    )

    assert result.analysis_status == "completed"
    assert "Гемоглобин 145" in result.extracted_text
    assert "ОАК" in result.extracted_text


def test_format_documents_for_context() -> None:
    """Recent documents should be rendered for the LLM prompt."""
    rendered = format_documents_for_context(
        1,
        [
            {
                "filename": "oak.txt",
                "description": "ОАК",
                "extracted_text": "Гемоглобин 145 г/л",
                "analysis_status": "completed",
                "created_at": "2026-05-21",
            }
        ]
    )

    assert "oak.txt" in rendered
    assert "Гемоглобин 145" in rendered


def test_upload_document_endpoint(tmp_path, monkeypatch) -> None:
    """Upload endpoint should store extracted text."""
    from app.routers import documents as documents_router

    monkeypatch.setattr(documents_router, "UPLOAD_DIR", tmp_path)

    sample = tmp_path / "sample.txt"
    sample.write_text("CRP 12", encoding="utf-8")

    with TestClient(app) as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        with sample.open("rb") as handle:
            response = client.post(
                "/api/documents",
                files={"file": ("sample.txt", handle, "text/plain")},
                data={"description": "Биохимия"},
            )

    assert response.status_code == 201
    payload = response.json()
    assert payload["description"] == "Биохимия"
    assert payload["analysis_status"] == "completed"
    assert "CRP 12" in payload["extracted_text"]
