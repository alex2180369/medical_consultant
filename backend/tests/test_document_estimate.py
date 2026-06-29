"""Tests for document cost estimation (phase 2)."""

from pathlib import Path

from app.services.document_cost_estimator import (
    HEAVY_IMAGE_BYTES,
    estimate_document_cost,
)
from tests.test_settings import make_test_settings


def test_estimate_text_file_is_free(tmp_path: Path) -> None:
    """Plain text uploads should not require confirmation."""
    path = tmp_path / "lab.txt"
    path.write_text("Гемоглобин 145", encoding="utf-8")

    estimate = estimate_document_cost(path, settings=make_test_settings())

    assert estimate.estimated_credits == 0
    assert estimate.requires_confirmation is False
    assert estimate.is_billable is False
    assert estimate.analysis_type == "text"


def test_estimate_large_image_requires_confirmation(tmp_path: Path) -> None:
    """Large images should trigger a confirmation warning."""
    path = tmp_path / "scan.jpg"
    path.write_bytes(b"\xff\xd8\xff" + b"\x00" * (HEAVY_IMAGE_BYTES + 1024))

    estimate = estimate_document_cost(path, settings=make_test_settings())

    assert estimate.is_billable is True
    assert estimate.analysis_type == "ocr"
    assert estimate.requires_confirmation is True
    assert estimate.estimated_credits >= 1


def test_estimate_endpoint(auth_client, tmp_path, monkeypatch) -> None:
    """Estimate endpoint should return zero cost for text files."""
    from app.routers import documents as documents_router

    monkeypatch.setattr(documents_router, "UPLOAD_DIR", tmp_path)

    sample = tmp_path / "sample.txt"
    sample.write_text("CRP 12", encoding="utf-8")

    with sample.open("rb") as handle:
        response = auth_client.post(
            "/api/documents/estimate",
            files={"file": ("sample.txt", handle, "text/plain")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["estimated_credits"] == 0
    assert payload["requires_confirmation"] is False


def test_upload_heavy_document_requires_confirmation(auth_client, tmp_path, monkeypatch) -> None:
    """Heavy uploads should return HTTP 428 without confirmation."""
    from app.routers import documents as documents_router

    monkeypatch.setattr(documents_router, "UPLOAD_DIR", tmp_path)

    sample = tmp_path / "scan.jpg"
    sample.write_bytes(b"\xff\xd8\xff" + b"\x00" * (HEAVY_IMAGE_BYTES + 2048))

    with sample.open("rb") as handle:
        response = auth_client.post(
            "/api/documents",
            files={"file": ("scan.jpg", handle, "image/jpeg")},
            data={"description": "Снимок"},
        )

    assert response.status_code == 428
    detail = response.json()["detail"]
    assert detail["estimate"]["requires_confirmation"] is True
