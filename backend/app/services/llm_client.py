"""OpenAI-compatible client for configured LLM providers."""

import logging
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.services.llm_router import LlmTask, resolve_model_route
from app.services.usage_service import (
    UsageContext,
    UsageLogResult,
    log_llm_usage,
    prepare_billable_request,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """Single chat message for an LLM request."""

    role: str
    content: str | list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token counts returned by the provider."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class ChatCompletionResult:
    """Text content returned by the LLM."""

    content: str
    model: str
    provider: str
    usage: TokenUsage | None = None
    usage_event_id: int | None = None
    billing: UsageLogResult | None = None


class LlmProviderError(RuntimeError):
    """Error returned by an LLM provider without sensitive request data."""


def _resolve_api_key(settings: Settings, provider: str) -> str | None:
    """Return the API key for the selected provider."""
    if provider == "aitunnel.ru":
        return settings.aitunnel_api_key
    if provider == "proxyapi.ru":
        return settings.proxyapi_api_key
    return None


def _resolve_base_url(settings: Settings, provider: str) -> str:
    """Return the base URL for the selected provider."""
    if provider == "proxyapi.ru":
        return settings.proxyapi_base_url.rstrip("/")
    return settings.aitunnel_base_url.rstrip("/")


def _parse_token_usage(data: dict[str, object]) -> TokenUsage | None:
    """Extract token usage from an OpenAI-compatible response."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
        return None
    if not isinstance(total_tokens, int):
        total_tokens = prompt_tokens + completion_tokens

    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def chat_completion(
    settings: Settings,
    task: LlmTask,
    messages: list[ChatMessage],
    *,
    temperature: float = 0.3,
    timeout: float = 120.0,
    usage_context: UsageContext | None = None,
) -> ChatCompletionResult:
    """Send a chat completion request to the configured provider."""
    route = resolve_model_route(task, settings)
    api_key = _resolve_api_key(settings, route.provider)

    if not api_key:
        raise RuntimeError(f"API key for provider {route.provider} is not configured.")

    if usage_context is not None:
        context = UsageContext(
            operation_type=usage_context.operation_type,
            user_id=usage_context.user_id,
            consultation_id=usage_context.consultation_id,
            complaint_id=usage_context.complaint_id,
            document_id=usage_context.document_id,
            task=usage_context.task or task,
            cache_hit=usage_context.cache_hit,
            billable=usage_context.billable,
        )
        prepare_billable_request(context)
    else:
        context = None

    payload = {
        "model": route.model,
        "messages": [
            {"role": message.role, "content": message.content} for message in messages
        ],
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{_resolve_base_url(settings, route.provider)}/chat/completions"

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            logger.warning(
                "LLM provider returned an error status. Provider=%s model=%s "
                "status=%s body=%r",
                route.provider,
                route.model,
                error.response.status_code,
                error.response.text[:1000],
            )
            raise LlmProviderError(
                f"LLM provider returned HTTP {error.response.status_code}."
            ) from error
        data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Unexpected LLM response format.") from error

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM returned an empty response.")

    usage = _parse_token_usage(data)
    billing: UsageLogResult | None = None
    usage_event_id: int | None = None

    if context is not None:
        billing = log_llm_usage(
            context=context,
            provider=route.provider,
            model=route.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )
        if billing is not None:
            usage_event_id = billing.event_id

    return ChatCompletionResult(
        content=content.strip(),
        model=route.model,
        provider=route.provider,
        usage=usage,
        usage_event_id=usage_event_id,
        billing=billing,
    )
