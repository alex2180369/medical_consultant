"""Model pricing and credit estimation for LLM usage tracking."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

from app.services.llm_router import LlmTask

CREDITS_PER_RUB = 10
MIN_CHARGE_CREDITS = 1


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Provider rates in RUB per 1000 tokens and tariff markup."""

    input_per_1k: Decimal
    output_per_1k: Decimal
    markup_multiplier: Decimal


DEFAULT_PRICING = ModelPricing(
    input_per_1k=Decimal("0.50"),
    output_per_1k=Decimal("1.50"),
    markup_multiplier=Decimal("1.30"),
)

MODEL_PRICING: dict[str, ModelPricing] = {
    "qwen3.5-plus-02-15": ModelPricing(
        Decimal("0.15"),
        Decimal("0.60"),
        Decimal("1.20"),
    ),
    "claude-sonnet-4.6": ModelPricing(
        Decimal("1.20"),
        Decimal("6.00"),
        Decimal("1.35"),
    ),
    "deepseek-r1-0528": ModelPricing(
        Decimal("0.40"),
        Decimal("1.60"),
        Decimal("1.40"),
    ),
    "claude-opus-4-7": ModelPricing(
        Decimal("3.00"),
        Decimal("15.00"),
        Decimal("1.50"),
    ),
    "gpt-4o-mini": ModelPricing(
        Decimal("0.10"),
        Decimal("0.40"),
        Decimal("1.25"),
    ),
}

TASK_MARKUP: dict[LlmTask, Decimal] = {
    LlmTask.SYMPTOMS: Decimal("1.20"),
    LlmTask.MEDICATIONS: Decimal("1.30"),
    LlmTask.COMPLEX_SYMPTOMS: Decimal("1.45"),
    LlmTask.REVIEW: Decimal("1.50"),
    LlmTask.IMAGING: Decimal("1.35"),
    LlmTask.NUTRITION: Decimal("1.25"),
    LlmTask.ADMIN_ENRICHMENT: Decimal("1.00"),
}


def resolve_pricing(model: str, task: LlmTask | None = None) -> ModelPricing:
    """Return pricing for a model, optionally adjusted by task tariff."""
    base = MODEL_PRICING.get(model, DEFAULT_PRICING)
    if task is None:
        return base

    task_markup = TASK_MARKUP.get(task, Decimal("1.30"))
    combined_markup = (base.markup_multiplier + task_markup) / Decimal("2")
    return ModelPricing(
        input_per_1k=base.input_per_1k,
        output_per_1k=base.output_per_1k,
        markup_multiplier=combined_markup,
    )


def calculate_usage_cost(
    *,
    model: str,
    task: LlmTask | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[Decimal, int]:
    """Return provider cost in RUB and estimated credits (not charged in phase 0)."""
    pricing = resolve_pricing(model, task)
    provider_cost = (
        Decimal(prompt_tokens) / Decimal(1000) * pricing.input_per_1k
        + Decimal(completion_tokens) / Decimal(1000) * pricing.output_per_1k
    )
    user_cost_rub = (provider_cost * pricing.markup_multiplier).quantize(
        Decimal("0.000001")
    )
    estimated_credits = max(
        MIN_CHARGE_CREDITS,
        int(
            (user_cost_rub * Decimal(CREDITS_PER_RUB)).quantize(
                Decimal("1"),
                rounding=ROUND_CEILING,
            )
        ),
    )
    return provider_cost, estimated_credits


# Approximate Yandex Vision OCR list price (~1.4 RUB / page) for usage logs.
YANDEX_OCR_PROVIDER_COST_PER_PAGE_RUB = Decimal("1.40")


def calculate_yandex_ocr_cost(
    *,
    page_count: int,
    credits_per_page: int,
) -> tuple[Decimal, int]:
    """Return provider cost and credits for Yandex Vision OCR pages."""
    pages = max(page_count, 1)
    provider_cost = (YANDEX_OCR_PROVIDER_COST_PER_PAGE_RUB * pages).quantize(
        Decimal("0.000001")
    )
    estimated_credits = max(MIN_CHARGE_CREDITS, pages * max(credits_per_page, 1))
    return provider_cost, estimated_credits
