"""Tests for ephemeral dialog mode (user «Апрель»)."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient

from app.database import ensure_user_profile, get_connection
from app.main import app
from app.services.consultation_service import continue_consultation
from app.services.ephemeral_session_service import (
    EPHEMERAL_DIALOG_CREDITS,
    is_ephemeral_dialog_user,
    start_new_ephemeral_dialog,
)
from app.services.wallet_service import admin_top_up, get_wallet, set_wallet_balance
from tests.test_settings import make_test_settings


def _make_april_user() -> str:
    user_id = f"april-{uuid.uuid4().hex[:8]}"
    ensure_user_profile(
        user_id,
        email=f"{user_id}@example.com",
        display_name="Апрель",
    )
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (
                id, email, password_hash, display_name, status, role
            )
            VALUES (%s, %s, %s, %s, 'approved', 'user')
            ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name
            """,
            (user_id, f"{user_id}@example.com", "x", "Апрель"),
        )
        connection.execute(
            """
            UPDATE profiles
            SET full_name = 'Апрель',
                age = 40,
                allergies = 'пыльца',
                notes = 'тест'
            WHERE user_id = %s
            """,
            (user_id,),
        )
    set_wallet_balance(
        user_id=user_id,
        credits=50,
        reason="test_setup",
    )
    return user_id


def test_is_ephemeral_dialog_user_detects_april() -> None:
    user_id = _make_april_user()
    assert is_ephemeral_dialog_user(user_id) is True
    ensure_user_profile("regular-user", email="r@example.com", display_name="Иван")
    assert is_ephemeral_dialog_user("regular-user") is False


def test_start_new_ephemeral_dialog_resets_state() -> None:
    user_id = _make_april_user()

    with get_connection() as connection:
        consultation = connection.execute(
            """
            INSERT INTO consultations (user_id, occurred_at, status)
            VALUES (%s, %s, 'active')
            RETURNING id
            """,
            (user_id, date(2026, 7, 21)),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO consultation_messages (consultation_id, role, content)
            VALUES (%s, 'user', 'симптом')
            """,
            (consultation["id"],),
        )
        connection.execute(
            """
            INSERT INTO complaints (
                user_id, symptoms, occurred_at, ai_status
            )
            VALUES (%s, 'кашель', %s, 'completed')
            """,
            (user_id, date(2026, 7, 20)),
        )

    result = start_new_ephemeral_dialog(user_id)

    assert result.wallet.credits_balance == EPHEMERAL_DIALOG_CREDITS
    assert result.profile.allergies == ""
    assert result.profile.age is None
    assert result.profile.notes == ""
    assert result.deleted_consultations >= 1
    assert result.deleted_complaints >= 1

    with get_connection() as connection:
        left = connection.execute(
            "SELECT COUNT(*) AS n FROM consultations WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        assert int(left["n"]) == 0
        left = connection.execute(
            "SELECT COUNT(*) AS n FROM complaints WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        assert int(left["n"]) == 0


def test_new_dialog_endpoint_forbidden_for_regular_user(auth_client: TestClient) -> None:
    response = auth_client.post("/api/consultations/new-dialog")
    assert response.status_code == 403


def test_conclusion_skips_history_for_april(monkeypatch) -> None:
    user_id = _make_april_user()
    admin_top_up(user_id=user_id, credits=500, admin_id="admin", note="test")

    from app.services import consultation_service

    def fake_chat_completion(
        settings, task, messages, *, temperature=0.3, timeout=120.0, usage_context=None
    ):
        from app.services.llm_client import ChatCompletionResult

        return ChatCompletionResult(
            content=(
                '{"phase":"conclusion","reply":"Готово.",'
                '"anamnesis_summary":"Кашель",'
                '"diagnoses":["ОРВИ"],'
                '"treatment_plan":"Покой",'
                '"doctor_questions":[],'
                '"urgency":"routine",'
                '"summary":"Ок"}'
            ),
            model="symptoms-model",
            provider="aitunnel.ru",
        )

    monkeypatch.setattr(consultation_service, "chat_completion", fake_chat_completion)

    result = continue_consultation(
        message="Кашель три дня",
        user_id=user_id,
        occurred_at=date(2026, 7, 21),
        settings=make_test_settings(aitunnel_api_key="test-key"),
    )

    assert result.phase == "conclusion"
    assert result.complaint is None

    with get_connection() as connection:
        complaints = connection.execute(
            "SELECT COUNT(*) AS n FROM complaints WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        assert int(complaints["n"]) == 0
        consultation = connection.execute(
            """
            SELECT status, complaint_id
            FROM consultations
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        assert consultation["status"] == "completed"
        assert consultation["complaint_id"] is None
