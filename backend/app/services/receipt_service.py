"""Consultation usage receipts for the account UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.database import get_connection

OPERATION_LABELS: dict[str, str] = {
    "chat_turn": "Диалог с консультантом",
    "chat_medications": "Проверка препаратов",
    "complaint": "Анализ жалобы",
    "complaint_medications": "Комментарий по препаратам",
    "ocr": "Распознавание документа",
    "nutrition": "ИИ-нутрициолог",
    "opinion_comparison": "Сравнение мнений",
    "admin_enrichment": "Анализ заявки (админ)",
}


@dataclass(frozen=True, slots=True)
class ReceiptLine:
    """Aggregated usage line for one operation/model pair."""

    operation_type: str
    operation_label: str
    model: str
    event_count: int
    total_tokens: int
    estimated_credits: int
    charged_credits: int


@dataclass(frozen=True, slots=True)
class ConsultationReceipt:
    """Usage receipt for one consultation session."""

    consultation_id: int
    occurred_at: date | None
    status: str
    complaint_id: int | None
    total_tokens: int
    total_estimated_credits: int
    total_charged_credits: int
    free_turns_used: int
    lines: list[ReceiptLine]
    generated_at: datetime


class ReceiptNotFoundError(LookupError):
    """Raised when a consultation receipt cannot be loaded."""


def get_consultation_receipt(*, consultation_id: int, user_id: str) -> ConsultationReceipt:
    """Return a usage receipt for one consultation owned by the user."""
    with get_connection() as connection:
        consultation = connection.execute(
            """
            SELECT id, occurred_at, status, complaint_id
            FROM consultations
            WHERE id = %s AND user_id = %s
            """,
            (consultation_id, user_id),
        ).fetchone()
        if consultation is None:
            raise ReceiptNotFoundError("Консультация не найдена.")

        rows = connection.execute(
            """
            SELECT
                operation_type,
                model,
                COUNT(*) AS event_count,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(estimated_credits), 0) AS estimated_credits,
                COALESCE(SUM(charged_credits), 0) AS charged_credits,
                COALESCE(
                    SUM(
                        CASE
                            WHEN is_charged = FALSE
                             AND estimated_credits > 0
                             AND cache_hit = FALSE
                            THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS free_turn_events
            FROM llm_usage_events
            WHERE consultation_id = %s AND user_id = %s
            GROUP BY operation_type, model
            ORDER BY operation_type, model
            """,
            (consultation_id, user_id),
        ).fetchall()

    lines = [
        ReceiptLine(
            operation_type=str(row["operation_type"]),
            operation_label=OPERATION_LABELS.get(
                str(row["operation_type"]),
                str(row["operation_type"]),
            ),
            model=str(row["model"]),
            event_count=int(row["event_count"]),
            total_tokens=int(row["total_tokens"]),
            estimated_credits=int(row["estimated_credits"]),
            charged_credits=int(row["charged_credits"]),
        )
        for row in rows
    ]

    return ConsultationReceipt(
        consultation_id=int(consultation["id"]),
        occurred_at=consultation["occurred_at"],
        status=str(consultation["status"]),
        complaint_id=consultation.get("complaint_id"),
        total_tokens=sum(line.total_tokens for line in lines),
        total_estimated_credits=sum(line.estimated_credits for line in lines),
        total_charged_credits=sum(line.charged_credits for line in lines),
        free_turns_used=sum(int(row["free_turn_events"]) for row in rows),
        lines=lines,
        generated_at=datetime.now(),
    )


def get_complaint_receipt(*, complaint_id: int, user_id: str) -> ConsultationReceipt:
    """Return a receipt for the consultation linked to a complaint."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id
            FROM consultations
            WHERE complaint_id = %s AND user_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (complaint_id, user_id),
        ).fetchone()

    if row is None:
        raise ReceiptNotFoundError("Для этого обращения нет данных консультации.")

    return get_consultation_receipt(consultation_id=int(row["id"]), user_id=user_id)
