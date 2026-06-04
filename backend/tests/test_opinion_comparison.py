"""Tests for opinion comparison."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services.opinion_comparison_service import compare_opinions


def _settings() -> Settings:
    """Build test settings."""
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
        proxyapi_base_url="https://api.proxyapi.ru/v1",
    )


def test_compare_opinions_without_api_key() -> None:
    """Comparison should fail gracefully without an API key."""
    with TestClient(app) as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        create_response = client.post(
            "/api/complaints",
            json={
                "symptoms": "Кашель",
                "doctor_feedback": "",
                "notes": "",
                "occurred_at": "2026-05-22",
            },
        )
        complaint_id = create_response.json()["id"]
        admin_user_id = client.get("/api/auth/me").json()["effective_user"]["id"]

    from app.database import get_connection

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE complaints
            SET
                ai_status = 'completed',
                ai_diagnosis = '• ОРВИ',
                ai_treatment = 'Покой',
                ai_analysis = 'Первое мнение'
            WHERE id = ?
            """,
            (complaint_id,),
        )

    updated, result = compare_opinions(
        complaint_id,
        "Врач назначил другой антибиотик",
        user_id=admin_user_id,
        settings=_settings(),
    )

    assert updated.doctor_feedback == "Врач назначил другой антибиотик"
    assert result.ai_status == "no_api_key"


def test_compare_opinions_endpoint(monkeypatch) -> None:
    """Compare endpoint should store comparison text."""
    from app.services import opinion_comparison_service

    def fake_chat_completion(
        settings, task, messages, *, temperature=0.3, timeout=120.0
    ):
        from app.services.llm_client import ChatCompletionResult

        return ChatCompletionResult(
            content=(
                '{"reply":"Мнения частично совпадают.",'
                '"agreements":"Оба указывают на инфекцию",'
                '"disagreements":"Разные антибиотики",'
                '"recommendations":"Обсудить с врачом",'
                '"questions_for_doctor":["Нужен ли контроль?"]}'
            ),
            model="review-model",
            provider="aitunnel.ru",
        )

    monkeypatch.setattr(
        opinion_comparison_service,
        "chat_completion",
        fake_chat_completion,
    )

    with TestClient(app) as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        create_response = client.post(
            "/api/complaints",
            json={
                "symptoms": "Кашель 10 дней",
                "doctor_feedback": "",
                "notes": "",
                "occurred_at": "2026-05-22",
            },
        )
        complaint_id = create_response.json()["id"]

    from app.database import get_connection

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE complaints
            SET
                ai_status = 'completed',
                ai_diagnosis = '• Постинфекционный кашель',
                ai_treatment = 'Симптоматическая терапия',
                ai_analysis = 'Первое мнение'
            WHERE id = ?
            """,
            (complaint_id,),
        )

    with TestClient(app) as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        response = client.post(
            f"/api/complaints/{complaint_id}/compare-opinions",
            json={"doctor_feedback": "ОРВИ, амоксициллин 5 дней"},
        )

    assert response.status_code == 200
    payload = response.json()
    comparison = json.loads(payload["ai_opinion_comparison"])
    assert comparison["reply"] == "Мнения частично совпадают."
    assert comparison["agreements"] == "Оба указывают на инфекцию"
    assert payload["doctor_feedback"] == "ОРВИ, амоксициллин 5 дней"
