"""Tests for complaint AI analysis."""

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ComplaintCreate
from app.services.symptom_analyzer import analyze_complaint
from tests.test_settings import make_test_settings


def test_analyze_complaint_without_api_key() -> None:
    """Analysis should gracefully skip when no API key is configured."""
    settings = make_test_settings()
    complaint = ComplaintCreate(
        symptoms="Головная боль и слабость",
        doctor_feedback="",
        notes="",
        occurred_at=date(2026, 5, 20),
    )

    result = analyze_complaint(complaint, settings=settings)

    assert result.ai_status == "no_api_key"
    assert "AITUNNEL_API_KEY" in result.ai_analysis


def test_create_complaint_returns_ai_fields(monkeypatch) -> None:
    """Creating a complaint should return AI analysis fields."""
    from app.services import symptom_analyzer

    def fake_analyze(
        _: ComplaintCreate,
        settings=None,
        *,
        analysis_mode="standard",
        user_id="test-user",
    ):
        return symptom_analyzer.SymptomAnalysisResult(
            ai_status="completed",
            ai_analysis="Краткое резюме",
            ai_diagnosis="• ОРВИ",
            ai_treatment="Покой, обильное питьё, обратиться к терапевту.",
            ai_doctor_questions="• Нужны ли анализы?",
            ai_urgency="routine",
        )

    monkeypatch.setattr(
        "app.routers.complaints.analyze_complaint",
        fake_analyze,
    )

    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer test-user"})
        response = client.post(
            "/api/complaints",
            json={
                "symptoms": "Насморк и кашель",
                "doctor_feedback": "",
                "notes": "",
                "occurred_at": "2026-05-20",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["ai_status"] == "completed"
    assert payload["ai_diagnosis"] == "• ОРВИ"
    assert payload["ai_treatment"]


def test_review_complaint_endpoint(monkeypatch) -> None:
    """Review endpoint should re-run analysis in review mode."""
    from app.services import symptom_analyzer

    calls: list[str] = []

    def fake_analyze(
        _: ComplaintCreate,
        settings=None,
        *,
        analysis_mode="standard",
        user_id="test-user",
    ):
        calls.append(analysis_mode)
        return symptom_analyzer.SymptomAnalysisResult(
            ai_status="completed",
            ai_analysis="Углублённый разбор",
            ai_diagnosis="• Гипотеза",
            ai_treatment="Подробный подход",
            ai_doctor_questions="• Вопрос врачу",
            ai_urgency="soon",
        )

    monkeypatch.setattr(
        "app.routers.complaints.analyze_complaint",
        fake_analyze,
    )

    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer test-user"})
        create_response = client.post(
            "/api/complaints",
            json={
                "symptoms": "Кашель",
                "doctor_feedback": "",
                "notes": "",
                "occurred_at": "2026-05-20",
            },
        )
        complaint_id = create_response.json()["id"]

        review_response = client.post(f"/api/complaints/{complaint_id}/review")

    assert review_response.status_code == 200
    payload = review_response.json()
    assert payload["ai_analysis"] == "Углублённый разбор"
    assert calls[-1] == "review"
