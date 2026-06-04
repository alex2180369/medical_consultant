"""OpenAI-compatible client for configured LLM providers."""

from dataclasses import dataclass

import httpx

from app.config import Settings
from app.services.llm_router import LlmTask, resolve_model_route


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """Single chat message for an LLM request."""

    role: str
    content: str | list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class ChatCompletionResult:
    """Text content returned by the LLM."""

    content: str
    model: str
    provider: str


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


def chat_completion(
    settings: Settings,
    task: LlmTask,
    messages: list[ChatMessage],
    *,
    temperature: float = 0.3,
    timeout: float = 120.0,
) -> ChatCompletionResult:
    """Send a chat completion request to the configured provider."""
    route = resolve_model_route(task, settings)
    api_key = _resolve_api_key(settings, route.provider)

    if not api_key:
        raise RuntimeError(f"API key for provider {route.provider} is not configured.")

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
            raise LlmProviderError(
                f"{error.response.status_code} {error.response.reason_phrase}: "
                f"{error.response.text[:1000]}"
            ) from error
        data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Unexpected LLM response format.") from error

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM returned an empty response.")

    return ChatCompletionResult(
        content=content.strip(),
        model=route.model,
        provider=route.provider,
    )
