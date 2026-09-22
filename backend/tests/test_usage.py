"""Tests for LLM usage tracking (phase 0)."""

from app.services.llm_router import LlmTask
from app.services.pricing import CREDITS_PER_RUB, calculate_usage_cost
from app.services.usage_service import (
    UsageContext,
    get_user_usage_summary,
    log_llm_usage,
)


def test_calculate_usage_cost_applies_task_markup() -> None:
    """Complex tasks should estimate higher credits than simple chat."""
    _, simple_credits = calculate_usage_cost(
        model="qwen3.5-plus-02-15",
        task=LlmTask.SYMPTOMS,
        prompt_tokens=1000,
        completion_tokens=500,
    )
    _, complex_credits = calculate_usage_cost(
        model="deepseek-r1-0528",
        task=LlmTask.COMPLEX_SYMPTOMS,
        prompt_tokens=1000,
        completion_tokens=500,
    )

    assert simple_credits >= 1
    assert complex_credits >= simple_credits


def test_log_llm_usage_persists_event(auth_client) -> None:
    """Usage events should be stored for authenticated users."""
    before = get_user_usage_summary("test-user").total_events

    result = log_llm_usage(
        context=UsageContext(
            user_id="test-user",
            operation_type="chat_turn",
            task=LlmTask.SYMPTOMS,
        ),
        provider="aitunnel.ru",
        model="qwen3.5-plus-02-15",
        prompt_tokens=1200,
        completion_tokens=300,
        total_tokens=1500,
    )

    assert result is not None
    assert result.event_id > 0

    summary = get_user_usage_summary("test-user")
    assert summary.total_events == before + 1
    assert summary.total_tokens >= 1500
    assert summary.total_estimated_credits >= 1
    assert summary.credits_per_rub == CREDITS_PER_RUB
    assert summary.by_operation["chat_turn"] >= 1


def test_admin_enrichment_is_not_billable_to_user(auth_client) -> None:
    """Admin enrichment should be logged with zero estimated credits."""
    before = get_user_usage_summary("test-user").total_events

    log_llm_usage(
        context=UsageContext(
            user_id="test-user",
            operation_type="admin_enrichment",
            task=LlmTask.ADMIN_ENRICHMENT,
            billable=False,
        ),
        provider="proxyapi.ru",
        model="gpt-4o-mini",
        prompt_tokens=500,
        completion_tokens=100,
        total_tokens=600,
    )

    summary = get_user_usage_summary("test-user")
    assert summary.total_events == before + 1
    assert summary.by_operation.get("admin_enrichment", 0) == 0


def test_usage_summary_endpoint(auth_client) -> None:
    """Account usage summary endpoint should return observability payload."""
    log_llm_usage(
        context=UsageContext(
            user_id="test-user",
            operation_type="nutrition",
            task=LlmTask.NUTRITION,
        ),
        provider="aitunnel.ru",
        model="claude-sonnet-4.6",
        prompt_tokens=800,
        completion_tokens=400,
        total_tokens=1200,
    )

    response = auth_client.get("/api/account/usage/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["billing_mode"] == "credits"
    assert payload["total_events"] >= 1
    assert payload["credits_per_rub"] == CREDITS_PER_RUB


def test_usage_events_endpoint(auth_client) -> None:
    """Account usage events endpoint should return recent rows."""
    response = auth_client.get("/api/account/usage/events?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
