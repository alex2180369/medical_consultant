"""Tests for document upload and consultation context."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.document_analyzer import (
    extract_document_text,
    format_documents_for_context,
    validate_uploaded_file,
)
from tests.test_settings import make_test_settings

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
MINIMAL_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_extract_text_file() -> None:
    """Plain text files should be readable without an API key."""
    path = Path("tests/fixtures/sample_lab.txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Гемоглобин 145 г/л", encoding="utf-8")

    result = extract_document_text(
        path,
        description="ОАК",
        settings=make_test_settings(),
    )

    assert result.analysis_status == "completed"
    assert "Гемоглобин 145" in result.extracted_text
    assert "ОАК" in result.extracted_text


def test_format_documents_for_context() -> None:
    """Recent documents should be rendered for the LLM prompt."""
    rendered = format_documents_for_context(
        "test-user",
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
        client.headers.update({"Authorization": "Bearer test-user"})
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


def test_delete_document_endpoint(tmp_path, monkeypatch) -> None:
    """Owner can delete a document; file and DB row are removed."""
    from app.routers import documents as documents_router

    monkeypatch.setattr(documents_router, "UPLOAD_DIR", tmp_path)

    sample = tmp_path / "sample.txt"
    sample.write_text("CRP 12", encoding="utf-8")

    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer test-user"})
        with sample.open("rb") as handle:
            upload = client.post(
                "/api/documents",
                files={"file": ("sample.txt", handle, "text/plain")},
                data={"description": "Биохимия"},
            )
        assert upload.status_code == 201
        document_id = upload.json()["id"]
        stored_path = Path(upload.json()["path"])
        assert stored_path.exists()

        deleted = client.delete(f"/api/documents/{document_id}")
        assert deleted.status_code == 204
        assert not stored_path.exists()

        missing = client.delete(f"/api/documents/{document_id}")
        assert missing.status_code == 404

        listed = client.get("/api/documents")
        assert listed.status_code == 200
        assert all(item["id"] != document_id for item in listed.json())


def test_validate_uploaded_file_accepts_supported_types(tmp_path: Path) -> None:
    """Known extensions with matching signatures should pass validation."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(MINIMAL_PDF)
    validate_uploaded_file(pdf, settings=make_test_settings())

    png = tmp_path / "scan.png"
    png.write_bytes(MINIMAL_PNG)
    validate_uploaded_file(png, settings=make_test_settings())

    text = tmp_path / "notes.txt"
    text.write_text("Гемоглобин 145", encoding="utf-8")
    validate_uploaded_file(text, settings=make_test_settings())


def test_validate_uploaded_file_rejects_unsupported_extension(
    tmp_path: Path,
) -> None:
    """Non-medical extensions should be rejected."""
    exe = tmp_path / "payload.exe"
    exe.write_bytes(b"MZ" + b"\x00" * 64)
    with pytest.raises(ValueError, match="Поддерживаются только"):
        validate_uploaded_file(exe, settings=make_test_settings())


def test_validate_uploaded_file_rejects_mismatched_signature(
    tmp_path: Path,
) -> None:
    """A renamed executable should be rejected by magic-byte check."""
    fake = tmp_path / "scan.pdf"
    fake.write_bytes(b"MZ" + b"\x00" * 64)
    with pytest.raises(ValueError, match="не похож"):
        validate_uploaded_file(fake, settings=make_test_settings())


def test_validate_uploaded_file_rejects_oversized_file(tmp_path: Path) -> None:
    """Files above the configured limit should be rejected."""
    large = tmp_path / "scan.png"
    large.write_bytes(MINIMAL_PNG + b"\x00" * 4096)
    with pytest.raises(ValueError, match="слишком большой"):
        validate_uploaded_file(
            large,
            settings=make_test_settings(),
            max_bytes=1024,
        )


def test_upload_endpoint_rejects_nonexistent_media(tmp_path, monkeypatch) -> None:
    """Uploading a spoofed .jpg should return HTTP 413/415 instead of storing."""
    from app.routers import documents as documents_router

    monkeypatch.setattr(documents_router, "UPLOAD_DIR", tmp_path)

    fake = tmp_path / "payload.jpg"
    fake.write_bytes(b"MZ" + b"\x00" * 64)

    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer test-user"})
        with fake.open("rb") as handle:
            response = client.post(
                "/api/documents",
                files={"file": ("payload.jpg", handle, "image/jpeg")},
            )

    assert response.status_code == 415
    assert list(tmp_path.glob("*_payload.jpg")) == []
