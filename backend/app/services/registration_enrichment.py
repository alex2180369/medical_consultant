"""AI-assisted analysis for registration applications."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.config import load_settings
from app.services.llm_client import ChatMessage, LlmProviderError, chat_completion
from app.services.llm_router import LlmTask


@dataclass(frozen=True, slots=True)
class RegistrationEnrichment:
    """Structured AI hints for an admin reviewing a registration."""

    suggested_name: str
    analysis: str
    confidence: str
    recommendation: str


def _extract_json_payload(content: str) -> dict[str, object]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response does not contain JSON.")

    return json.loads(text[start : end + 1])


def _fallback_enrichment(email: str, display_name: str) -> RegistrationEnrichment:
    local_part = email.split("@", 1)[0]
    parts = [part for part in re.split(r"[._\-+]+", local_part) if part]
    suggested = " ".join(part.capitalize() for part in parts[:3]) if parts else display_name
    return RegistrationEnrichment(
        suggested_name=suggested,
        analysis=(
            "Автоматический анализ недоступен. "
            f"Имя из заявки: {display_name or 'не указано'}."
        ),
        confidence="low",
        recommendation="Проверьте имя и email вручную перед одобрением.",
    )


def enrich_registration(*, email: str, display_name: str) -> RegistrationEnrichment:
    """Analyze a registration application and return admin hints."""
    settings = load_settings()
    if not settings.proxyapi_api_key and not settings.aitunnel_api_key:
        return _fallback_enrichment(email, display_name)

    prompt = (
        "Проанализируй заявку на регистрацию в медицинском сервисе.\n"
        "Ты не имеешь доступа к внешним базам данных. "
        "Опирайся только на email и имя из заявки.\n\n"
        f"Email: {email}\n"
        f"Имя из заявки: {display_name or 'не указано'}\n\n"
        "Верни ТОЛЬКО валидный JSON без markdown:\n"
        "{\n"
        '  "suggested_name": "предполагаемое ФИО из email",\n'
        '  "confidence": "low|medium|high",\n'
        '  "analysis": "краткий анализ согласованности имени и email",\n'
        '  "recommendation": "рекомендация администратору"\n'
        "}"
    )

    try:
        result = chat_completion(
            settings,
            LlmTask.ADMIN_ENRICHMENT,
            [
                ChatMessage(
                    role="system",
                    content=(
                        "Ты помощник администратора. "
                        "Отвечай только JSON-объектом на русском языке."
                    ),
                ),
                ChatMessage(role="user", content=prompt),
            ],
            temperature=0.1,
            timeout=45.0,
        )
        payload = _extract_json_payload(result.content)
    except (LlmProviderError, ValueError, json.JSONDecodeError, RuntimeError):
        return _fallback_enrichment(email, display_name)

    suggested_name = str(payload.get("suggested_name", "")).strip()
    analysis = str(payload.get("analysis", "")).strip()
    confidence = str(payload.get("confidence", "low")).strip().lower()
    recommendation = str(payload.get("recommendation", "")).strip()

    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    if not suggested_name:
        suggested_name = _fallback_enrichment(email, display_name).suggested_name

    if not analysis:
        analysis = _fallback_enrichment(email, display_name).analysis

    if not recommendation:
        recommendation = "Проверьте данные заявки вручную."

    return RegistrationEnrichment(
        suggested_name=suggested_name,
        analysis=analysis,
        confidence=confidence,
        recommendation=recommendation,
    )
