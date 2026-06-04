"""AI-assisted weekly nutrition plan generation."""

import json
import re

from app.config import Settings, load_settings
from app.schemas import ComplaintRecord, MedicalProfile, NutritionPlanResponse
from app.services.llm_client import ChatMessage, chat_completion
from app.services.llm_router import LlmTask, resolve_model_route

NUTRITION_SYSTEM_PROMPT = """
Ты ИИ-нутрициолог для семейного локального медицинского приложения.
Ты не врач и не назначаешь лечение. Твоя задача — составить реалистичное
домашнее меню на неделю с учётом профиля здоровья, аллергий, лекарств,
последних обращений и продуктов, которые уже есть дома.

Требования:
- меню на 7 дней: monday, tuesday, wednesday, thursday, friday, saturday, sunday;
- каждый день содержит 3 приёма пищи: breakfast, lunch, dinner;
- блюда простые, домашние, без острых блюд, редких соусов и дорогих морепродуктов;
- не повторяй блюда и одинаковые гарниры подряд;
- чередуй курицу, мясо, рыбу, яйца, крупы, овощи, молочные продукты;
- учитывай продукты дома и не добавляй лишние покупки в блюда без необходимости;
- формулируй дружелюбно и кратко.

Верни строго JSON без markdown:
{
  "menu": [
    {
      "id": "monday",
      "title": "Понедельник",
      "subtitle": "короткая фраза дня",
      "meals": [
        {
          "type": "breakfast|lunch|dinner",
          "label": "Завтрак|Обед|Ужин",
          "title": "название блюда",
          "description": "короткое описание",
          "prepTime": "15 минут",
          "difficulty": "легко|средне",
          "tags": ["быстро", "полезно"],
          "cookMethod": "как готовить, температура/время если нужно",
          "ingredients": ["ингредиент 1", "ингредиент 2"],
          "steps": ["шаг 1", "шаг 2", "шаг 3"],
          "macros": {
            "calories": 450,
            "protein": 25,
            "fat": 15,
            "carbs": 55
          }
        }
      ]
    }
  ]
}
""".strip()


def _extract_json(content: str) -> dict[str, object]:
    """Parse JSON from a model response."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("LLM response is not valid JSON.")


def _format_complaints(complaints: list[ComplaintRecord]) -> str:
    if not complaints:
        return (
            "Пользователь не дал согласие учитывать рекомендации "
            "медконсультанта или рекомендаций пока нет."
        )

    lines: list[str] = []
    for item in complaints[:5]:
        lines.append(
            f"- {item.occurred_at}: {item.symptoms}; "
            f"диагноз/гипотезы: {item.ai_diagnosis or 'нет'}; "
            f"тактика и питание: {item.ai_treatment or item.ai_analysis or 'нет'}; "
            f"срочность: {item.ai_urgency or 'нет данных'}"
        )
    return "\n".join(lines)


def _build_user_prompt(
    profile: MedicalProfile,
    complaints: list[ComplaintRecord],
    pantry_items: list[str],
    include_medical_recommendations: bool,
) -> str:
    """Build a nutrition planning prompt."""
    pantry = ", ".join(pantry_items) if pantry_items else "не указаны"
    sleep_text = (
        str(profile.sleep_hours)
        if profile.sleep_hours is not None
        else "нет данных"
    )
    consent_text = "да" if include_medical_recommendations else "нет"

    return f"""
Профиль пользователя:
- Имя: {profile.full_name or "не указано"}
- Возраст: {profile.age if profile.age is not None else "не указан"}
- Пол: {profile.sex or "не указан"}
- Рост: {profile.height_cm if profile.height_cm is not None else "не указан"} см
- Вес: {profile.weight_kg if profile.weight_kg is not None else "не указан"} кг
- Диабет: {profile.diabetes_status or "нет данных"}
- Сердечно-сосудистые заболевания: {profile.cardiovascular_status or "нет данных"}
- Хронические заболевания: {profile.chronic_conditions or "нет данных"}
- Аллергии: {profile.allergies or "нет данных"}
- Лекарства: {profile.medications or "нет данных"}
- Физическая активность: {profile.activity_level or "нет данных"}
- Курение: {profile.smoking_status or "нет данных"}
- Сон: {sleep_text} ч/сутки
- Стресс: {profile.stress_level or "нет данных"}
- Семейная история: {profile.family_history or "нет данных"}

Рекомендации медконсультанта:
Согласие пользователя на учёт рекомендаций: {consent_text}
{_format_complaints(complaints)}

Продукты дома:
{pantry}

Любимые блюда и предпочтения:
омлет, сырники, драники, овсянка, гречка, рис, паста, курица,
свинина, говядина, рыба, овощные салаты, суп, картофель, творог,
йогурт, бутерброды, запеканки.

Составь обновлённое меню на неделю в указанном JSON-формате.
""".strip()


def generate_weekly_nutrition_plan(
    profile: MedicalProfile,
    complaints: list[ComplaintRecord],
    pantry_items: list[str],
    include_medical_recommendations: bool = False,
    settings: Settings | None = None,
) -> NutritionPlanResponse:
    """Generate a weekly menu with the configured nutrition model."""
    settings = settings or load_settings()
    route = resolve_model_route(LlmTask.NUTRITION, settings)

    if not settings.aitunnel_api_key:
        return NutritionPlanResponse(
            ai_status="no_api_key",
            message=(
                "Для обновления меню нужен AITUNNEL_API_KEY в локальном `.env`."
            ),
        )

    try:
        completion = chat_completion(
            settings,
            LlmTask.NUTRITION,
            messages=[
                ChatMessage(role="system", content=NUTRITION_SYSTEM_PROMPT),
                ChatMessage(
                    role="user",
                    content=_build_user_prompt(
                        profile,
                        complaints,
                        pantry_items,
                        include_medical_recommendations,
                    ),
                ),
            ],
            temperature=0.4,
            timeout=180.0,
        )
        payload = _extract_json(completion.content)
    except Exception as error:
        return NutritionPlanResponse(
            ai_status="failed",
            message=f"Не удалось обновить меню ({route.model}): {error}",
        )

    menu = payload.get("menu")
    if not isinstance(menu, list) or not menu:
        return NutritionPlanResponse(
            ai_status="failed",
            message=f"Модель {route.model} вернула меню в неверном формате.",
        )

    return NutritionPlanResponse(
        ai_status="completed",
        message=f"Меню обновлено моделью {route.model}.",
        menu=menu,
    )
