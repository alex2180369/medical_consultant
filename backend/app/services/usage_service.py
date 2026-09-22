"""LLM usage logging and wallet charging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.database import get_connection
from app.services.llm_router import LlmTask
from app.services.pricing import (
    CREDITS_PER_RUB,
    calculate_usage_cost,
    calculate_yandex_ocr_cost,
)
from app.services.wallet_service import (
    InsufficientCreditsError,
    apply_usage_charge,
    ensure_llm_allowed,
)

OperationType = Literal[
    "chat_turn",
    "chat_medications",
    "complaint",
    "complaint_medications",
    "ocr",
    "nutrition",
    "opinion_comparison",
    "admin_enrichment",
]


@dataclass(frozen=True, slots=True)
class UsageContext:
    """Metadata attached to a billed LLM operation."""

    operation_type: OperationType
    user_id: str | None = None
    consultation_id: int | None = None
    complaint_id: int | None = None
    document_id: int | None = None
    task: LlmTask | None = None
    cache_hit: bool = False
    billable: bool = True


@dataclass(frozen=True, slots=True)
class UsageLogResult:
    """Persisted usage event with billing outcome."""

    event_id: int
    estimated_credits: int
    charged_credits: int
    balance_remaining: int
    free_turns_remaining: int
    used_free_turn: bool
    is_charged: bool
    total_tokens: int
    model: str


@dataclass(frozen=True, slots=True)
class UsageEventRecord:
    """Persisted LLM usage event."""

    id: int
    user_id: str | None
    consultation_id: int | None
    complaint_id: int | None
    document_id: int | None
    operation_type: str
    llm_task: str | None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider_cost_rub: Decimal
    estimated_credits: int
    charged_credits: int
    cache_hit: bool
    is_charged: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """Aggregated usage for a user."""

    total_events: int
    total_tokens: int
    total_estimated_credits: int
    total_charged_credits: int
    credits_per_rub: int
    by_operation: dict[str, int]


def prepare_billable_request(context: UsageContext) -> None:
    """Reject billable LLM calls when the wallet cannot afford them."""
    if not context.billable or not context.user_id or context.cache_hit:
        return
    ensure_llm_allowed(context.user_id)


def log_llm_usage(
    *,
    context: UsageContext,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> UsageLogResult | None:
    """Persist one LLM usage event and apply wallet charging when billable."""
    if context.cache_hit:
        provider_cost = Decimal("0")
        estimated_credits = 0
    elif context.billable:
        provider_cost, estimated_credits = calculate_usage_cost(
            model=model,
            task=context.task,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    else:
        provider_cost, estimated_credits = calculate_usage_cost(
            model=model,
            task=context.task,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        estimated_credits = 0

    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO llm_usage_events (
                user_id,
                consultation_id,
                complaint_id,
                document_id,
                operation_type,
                llm_task,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                provider_cost_rub,
                estimated_credits,
                charged_credits,
                cache_hit,
                is_charged
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, FALSE)
            RETURNING id
            """,
            (
                context.user_id,
                context.consultation_id,
                context.complaint_id,
                context.document_id,
                context.operation_type,
                context.task.value if context.task else None,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                provider_cost,
                estimated_credits,
                context.cache_hit,
            ),
        ).fetchone()

    event_id = int(row["id"])

    if not context.user_id:
        return None

    charge = apply_usage_charge(
        user_id=context.user_id,
        usage_event_id=event_id,
        estimated_credits=estimated_credits,
        billable=context.billable and not context.cache_hit,
    )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE llm_usage_events
            SET charged_credits = %s
            WHERE id = %s
            """,
            (charge.charged_credits, event_id),
        )

    return UsageLogResult(
        event_id=event_id,
        estimated_credits=charge.estimated_credits,
        charged_credits=charge.charged_credits,
        balance_remaining=charge.balance_remaining,
        free_turns_remaining=charge.free_turns_remaining,
        used_free_turn=charge.used_free_turn,
        is_charged=charge.is_charged,
        total_tokens=total_tokens,
        model=model,
    )


def log_ocr_usage(
    *,
    context: UsageContext,
    provider: str,
    model: str,
    page_count: int,
    credits_per_page: int,
) -> UsageLogResult | None:
    """Persist a Yandex OCR usage event and charge the wallet when billable."""
    provider_cost, estimated_credits = calculate_yandex_ocr_cost(
        page_count=page_count,
        credits_per_page=credits_per_page,
    )
    if not context.billable or context.cache_hit:
        estimated_credits = 0

    pages = max(page_count, 1)
    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO llm_usage_events (
                user_id,
                consultation_id,
                complaint_id,
                document_id,
                operation_type,
                llm_task,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                provider_cost_rub,
                estimated_credits,
                charged_credits,
                cache_hit,
                is_charged
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, FALSE)
            RETURNING id
            """,
            (
                context.user_id,
                context.consultation_id,
                context.complaint_id,
                context.document_id,
                context.operation_type,
                "ocr",
                provider,
                model,
                pages,
                0,
                pages,
                provider_cost,
                estimated_credits,
                context.cache_hit,
            ),
        ).fetchone()

    event_id = int(row["id"])
    if not context.user_id:
        return None

    charge = apply_usage_charge(
        user_id=context.user_id,
        usage_event_id=event_id,
        estimated_credits=estimated_credits,
        billable=context.billable and not context.cache_hit,
    )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE llm_usage_events
            SET charged_credits = %s
            WHERE id = %s
            """,
            (charge.charged_credits, event_id),
        )

    return UsageLogResult(
        event_id=event_id,
        estimated_credits=charge.estimated_credits,
        charged_credits=charge.charged_credits,
        balance_remaining=charge.balance_remaining,
        free_turns_remaining=charge.free_turns_remaining,
        used_free_turn=charge.used_free_turn,
        is_charged=charge.is_charged,
        total_tokens=pages,
        model=model,
    )


def get_user_usage_summary(user_id: str) -> UsageSummary:
    """Return aggregated usage metrics for one user."""
    with get_connection() as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total_events,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(estimated_credits), 0) AS total_estimated_credits,
                COALESCE(SUM(charged_credits), 0) AS total_charged_credits
            FROM llm_usage_events
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT operation_type, COALESCE(SUM(charged_credits), 0) AS credits
            FROM llm_usage_events
            WHERE user_id = %s
            GROUP BY operation_type
            ORDER BY operation_type
            """,
            (user_id,),
        ).fetchall()

    by_operation = {str(row["operation_type"]): int(row["credits"]) for row in rows}
    return UsageSummary(
        total_events=int(totals["total_events"]),
        total_tokens=int(totals["total_tokens"]),
        total_estimated_credits=int(totals["total_estimated_credits"]),
        total_charged_credits=int(totals["total_charged_credits"]),
        credits_per_rub=CREDITS_PER_RUB,
        by_operation=by_operation,
    )


def list_user_usage_events(user_id: str, *, limit: int = 50) -> list[UsageEventRecord]:
    """Return recent usage events for one user."""
    safe_limit = max(1, min(limit, 200))
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM llm_usage_events
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, safe_limit),
        ).fetchall()

    return [_row_to_event(dict(row)) for row in rows]


def _row_to_event(row: dict[str, Any]) -> UsageEventRecord:
    return UsageEventRecord(
        id=int(row["id"]),
        user_id=row.get("user_id"),
        consultation_id=row.get("consultation_id"),
        complaint_id=row.get("complaint_id"),
        document_id=row.get("document_id"),
        operation_type=str(row["operation_type"]),
        llm_task=row.get("llm_task"),
        provider=str(row["provider"]),
        model=str(row["model"]),
        prompt_tokens=int(row["prompt_tokens"]),
        completion_tokens=int(row["completion_tokens"]),
        total_tokens=int(row["total_tokens"]),
        provider_cost_rub=Decimal(str(row["provider_cost_rub"])),
        estimated_credits=int(row["estimated_credits"]),
        charged_credits=int(row.get("charged_credits") or 0),
        cache_hit=bool(row["cache_hit"]),
        is_charged=bool(row["is_charged"]),
        created_at=row["created_at"],
    )


__all__ = [
    "InsufficientCreditsError",
    "OperationType",
    "UsageContext",
    "UsageEventRecord",
    "UsageLogResult",
    "UsageSummary",
    "get_user_usage_summary",
    "list_user_usage_events",
    "log_llm_usage",
    "log_ocr_usage",
    "prepare_billable_request",
]
