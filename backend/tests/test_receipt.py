"""Tests for consultation usage receipts (phase 2)."""

from datetime import date

from app.database import get_connection
from app.services.llm_router import LlmTask
from app.services.usage_service import UsageContext, log_llm_usage


def _seed_consultation_with_usage(*, user_id: str = "test-user") -> tuple[int, int]:
    with get_connection() as connection:
        complaint_row = connection.execute(
            """
            INSERT INTO complaints (
                user_id,
                symptoms,
                doctor_feedback,
                notes,
                occurred_at,
                ai_status
            )
            VALUES (%s, %s, %s, %s, %s, 'completed')
            RETURNING id
            """,
            (user_id, "Кашель", "ОРВИ", "", date(2026, 5, 22)),
        ).fetchone()
        complaint_id = int(complaint_row["id"])

        consultation_row = connection.execute(
            """
            INSERT INTO consultations (
                user_id,
                occurred_at,
                doctor_feedback,
                notes,
                status,
                complaint_id
            )
            VALUES (%s, %s, %s, %s, 'completed', %s)
            RETURNING id
            """,
            (user_id, date(2026, 5, 22), "ОРВИ", "", complaint_id),
        ).fetchone()
        consultation_id = int(consultation_row["id"])

    log_llm_usage(
        context=UsageContext(
            operation_type="chat_turn",
            user_id=user_id,
            consultation_id=consultation_id,
            task=LlmTask.SYMPTOMS,
        ),
        provider="aitunnel.ru",
        model="symptoms-model",
        prompt_tokens=500,
        completion_tokens=200,
        total_tokens=700,
    )
    log_llm_usage(
        context=UsageContext(
            operation_type="chat_medications",
            user_id=user_id,
            consultation_id=consultation_id,
            task=LlmTask.MEDICATIONS,
        ),
        provider="aitunnel.ru",
        model="symptoms-model",
        prompt_tokens=300,
        completion_tokens=150,
        total_tokens=450,
    )

    return consultation_id, complaint_id


def test_consultation_receipt_endpoint(auth_client) -> None:
    """Consultation receipt should aggregate usage events."""
    consultation_id, _ = _seed_consultation_with_usage()

    response = auth_client.get(f"/api/consultations/{consultation_id}/receipt")

    assert response.status_code == 200
    payload = response.json()
    assert payload["consultation_id"] == consultation_id
    assert payload["total_charged_credits"] >= 0
    assert len(payload["lines"]) >= 1
    assert any(line["operation_type"] == "chat_turn" for line in payload["lines"])


def test_complaint_receipt_endpoint(auth_client) -> None:
    """Complaint receipt should resolve the linked consultation."""
    consultation_id, complaint_id = _seed_consultation_with_usage()

    response = auth_client.get(f"/api/complaints/{complaint_id}/receipt")

    assert response.status_code == 200
    payload = response.json()
    assert payload["consultation_id"] == consultation_id
    assert payload["complaint_id"] == complaint_id


def test_consultation_receipt_not_found(auth_client) -> None:
    """Unknown consultation receipts should return 404."""
    response = auth_client.get("/api/consultations/999999/receipt")
    assert response.status_code == 404
