"""Tests for opinion comparison."""

import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.opinion_comparison_service import compare_opinions
from tests.test_settings import make_test_settings


def test_compare_opinions_without_api_key(auth_client: TestClient) -> None:
    """Comparison should fail gracefully without an API key."""
    create_response = auth_client.post(
        "/api/complaints",
        json={
            "symptoms": "Кашель",
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
                ai_diagnosis = '• ОРВИ',
                ai_treatment = 'Покой',
                ai_analysis = 'Первое мнение'
            WHERE id = %s
            """,
            (complaint_id,),
        )

    updated, result = compare_opinions(
        complaint_id,
        "Врач назначил другой антибиотик",
        user_id="test-user",
        settings=make_test_settings(),
    )

    assert updated.doctor_feedback == "Врач назначил другой антибиотик"
    assert result.ai_status == "no_api_key"


def test_compare_opinions_endpoint(monkeypatch, auth_client: TestClient) -> None:
    """Compare endpoint should store comparison text."""
    from app.services import opinion_comparison_service

    def fake_compare(complaint_id, doctor_feedback, user_id, settings=None):
        from app.schemas import ComplaintRecord
        from datetime import date, datetime

        return (
            ComplaintRecord(
                id=complaint_id,
                symptoms="Кашель",
                doctor_feedback=doctor_feedback,
                notes="",
                occurred_at=date(2026, 5, 22),
                created_at=datetime(2026, 5, 22, 12, 0, 0),
                ai_status="completed",
                ai_opinion_comparison=json.dumps(
                    {"summary": "Мнения частично совпадают"}
                ),
            ),
            opinion_comparison_service.OpinionComparisonResult(
                ai_status="completed",
                ai_opinion_comparison=json.dumps(
                    {"summary": "Мнения частично совпадают"}
                ),
            ),
        )

    monkeypatch.setattr(
        "app.routers.complaints.compare_opinions",
        fake_compare,
    )

    create_response = auth_client.post(
        "/api/complaints",
        json={
            "symptoms": "Кашель",
            "doctor_feedback": "",
            "notes": "",
            "occurred_at": "2026-05-22",
        },
    )
    complaint_id = create_response.json()["id"]

    response = auth_client.post(
        f"/api/complaints/{complaint_id}/compare-opinions",
        json={"doctor_feedback": "Врач назначил другой антибиотик"},
    )

    assert response.status_code == 200
    payload = response.json()
    comparison = json.loads(payload["ai_opinion_comparison"])
    assert comparison["summary"] == "Мнения частично совпадают"
