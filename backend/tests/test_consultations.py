"""Tests for multi-turn consultation chat."""

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.services.consultation_service import continue_consultation
from tests.test_settings import make_test_settings


def test_consultation_without_api_key() -> None:
    """Consultation should respond gracefully without an API key."""
    settings = make_test_settings()

    result = continue_consultation(
        message="После визита к терапевту осталась слабость",
        user_id="test-user",
        occurred_at=date(2026, 5, 22),
        settings=settings,
    )

    assert result.ai_status == "no_api_key"
    assert result.phase == "anamnesis"
    assert "AITUNNEL_API_KEY" in result.reply


def test_consultation_chat_anamnesis_turn(monkeypatch) -> None:
    """Chat endpoint should return an anamnesis question on early turns."""
    from app.services import consultation_service

    def fake_chat_completion(
        settings, task, messages, *, temperature=0.3, timeout=120.0, usage_context=None
    ):
        from app.services.llm_client import ChatCompletionResult

        return ChatCompletionResult(
            content=(
                '{"phase":"anamnesis","reply":"Когда начались симптомы?",'
                '"anamnesis_summary":"","diagnoses":[],"treatment_plan":"",'
                '"comparison_with_doctor":"","doctor_questions":[],"urgency":"",'
                '"summary":""}'
            ),
            model="symptoms-model",
            provider="aitunnel.ru",
        )

    monkeypatch.setattr(
        consultation_service,
        "chat_completion",
        fake_chat_completion,
    )
    monkeypatch.setattr(
        consultation_service,
        "load_settings",
        lambda: make_test_settings(aitunnel_api_key="test-key"),
    )

    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer test-user"})
        response = client.post(
            "/api/consultations/chat",
            json={
                "message": "После визита назначили антибиотик, но кашель остался",
                "occurred_at": "2026-05-22",
                "doctor_feedback": "ОРВИ",
                "notes": "Температура 37.2",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "anamnesis"
    assert payload["reply"] == "Когда начались симптомы?"
    assert payload["complaint"] is None


def test_consultation_chat_conclusion_turn(monkeypatch) -> None:
    """Chat endpoint should save a complaint when the model concludes."""
    from app.services import consultation_service

    def fake_chat_completion(
        settings, task, messages, *, temperature=0.3, timeout=120.0, usage_context=None
    ):
        from app.services.llm_client import ChatCompletionResult

        return ChatCompletionResult(
            content=(
                '{"phase":"conclusion","reply":"Первое мнение сформировано.",'
                '"anamnesis_summary":"Кашель после ОРВИ",'
                '"diagnoses":["Постинфекционный кашель"],'
                '"treatment_plan":"Согласовать с врачом симптоматическую терапию",'
                '"doctor_questions":["Нужен ли контрольный осмотр?"],'
                '"urgency":"routine",'
                '"summary":"Состояние, вероятно, не требует срочной помощи."}'
            ),
            model="symptoms-model",
            provider="aitunnel.ru",
        )

    monkeypatch.setattr(
        consultation_service,
        "chat_completion",
        fake_chat_completion,
    )
    monkeypatch.setattr(
        consultation_service,
        "load_settings",
        lambda: make_test_settings(aitunnel_api_key="test-key"),
    )

    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer test-user"})
        response = client.post(
            "/api/consultations/chat",
            json={
                "message": "Кашель 10 дней, антибиотик не помог",
                "occurred_at": "2026-05-22",
                "doctor_feedback": "ОРВИ, амоксициллин",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "conclusion"
    assert payload["complaint"] is not None
    assert payload["complaint"]["ai_diagnosis"] == "• Постинфекционный кашель"
    assert payload["complaint"]["ai_status"] == "completed"
