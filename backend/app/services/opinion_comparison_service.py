"""Compare assistant first opinion with in-person doctor opinion."""

import json
import re
from dataclasses import dataclass

from app.config import Settings, load_settings
from app.database import get_connection
from app.schemas import ComplaintRecord, MedicalProfile
from app.services.llm_client import ChatMessage, chat_completion
from app.services.llm_router import LlmTask, resolve_model_route
from app.services.usage_service import UsageContext
from app.services.wallet_service import InsufficientCreditsError
from app.services.symptom_analyzer import (
    _load_profile,
    _load_recent_labs,
)

COMPARISON_SYSTEM_PROMPT = """
Ты медицинский информационный ассистент для личного использования в РФ.

Сценарий:
1) Ассистент ранее дал пациенту ПЕРВОЕ мнение (до визита к врачу).
2) Пациент сходил к врачу и получил ВТОРОЕ мнение (очный осмотр).
3) Нужно помочь сравнить оба мнения и понять, что делать дальше.

Правила:
- Чётко раздели: первое мнение ассистента vs второе мнение врача.
- В agreements — только то, где диагноз или лечение совпадают.
- В disagreements — только реальные расхождения;
  если их нет — напиши «Существенных расхождений нет».
- В recommendations — конкретные шаги для пациента
  (что делать, что не менять самостоятельно).
- В questions_for_doctor — 2–4 вопроса для повторного приёма, если есть сомнения.
- Не отменяй назначения врача и не выдавай себя за лечащего врача.
- Пиши простым языком на русском, без markdown.

Ответ верни строго в JSON без markdown-обёртки:
{
  "reply": "краткий общий вывод в 2–4 предложениях",
  "agreements": "где мнения совпадают (диагноз, тактика, назначения)",
  "disagreements": "где мнения расходятся или что уточнить",
  "recommendations": "что делать дальше: следовать назначениям врача, что отслеживать",
  "questions_for_doctor": ["вопрос 1", "вопрос 2"]
}
""".strip()


@dataclass(frozen=True, slots=True)
class OpinionComparisonResult:
    """Structured comparison of two medical opinions."""

    ai_status: str
    ai_opinion_comparison: str


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


def _fetch_complaint(complaint_id: int, user_id: str) -> ComplaintRecord:
    """Load a complaint by id."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM complaints WHERE id = %s AND user_id = %s",
            (complaint_id, user_id),
        ).fetchone()

    if row is None:
        raise ValueError("Complaint not found.")

    return ComplaintRecord(**dict(row))


def _build_comparison_prompt(
    complaint: ComplaintRecord,
    profile: MedicalProfile,
    labs: list[str],
) -> str:
    """Build user prompt with both opinions."""
    lab_block = "\n".join(f"- {item}" for item in labs) if labs else "Нет данных."
    sleep_text = (
        str(profile.sleep_hours)
        if profile.sleep_hours is not None
        else "нет данных"
    )
    bmi = ""
    if profile.height_cm and profile.weight_kg and profile.height_cm > 0:
        height_m = profile.height_cm / 100
        bmi = f"{profile.weight_kg / (height_m * height_m):.1f}"

    return f"""
Профиль пациента:
- Возраст: {profile.age if profile.age is not None else "не указан"}
- Пол: {profile.sex or "не указан"}
- Группа крови: {profile.blood_type or "не указана"}
- Рост: {profile.height_cm if profile.height_cm is not None else "не указан"} см
- Вес: {profile.weight_kg if profile.weight_kg is not None else "не указан"} кг
- ИМТ: {bmi or "не рассчитан"}
- Диабет: {profile.diabetes_status or "нет данных"}
- Сердечно-сосудистые заболевания: {profile.cardiovascular_status or "нет данных"}
- Хронические заболевания: {profile.chronic_conditions or "нет данных"}
- Аллергии: {profile.allergies or "нет данных"}
- Текущие препараты: {profile.medications or "нет данных"}
- Образ жизни: {profile.lifestyle or "нет данных"}
- Физическая активность: {profile.activity_level or "нет данных"}
- Курение: {profile.smoking_status or "нет данных"}
- Сон: {sleep_text} ч/сутки
- Стресс: {profile.stress_level or "нет данных"}

Последние анализы:
{lab_block}

Анамнез (со слов пациента):
{complaint.symptoms}

ПЕРВОЕ МНЕНИЕ (ассистент, до визита к врачу):
- Диагноз/гипотезы: {complaint.ai_diagnosis or "не сформировано"}
- План лечения: {complaint.ai_treatment or "не сформирован"}
- Резюме: {complaint.ai_analysis or "нет"}

ВТОРОЕ МНЕНИЕ (очный врач, после визита):
{complaint.doctor_feedback}

Наблюдения пациента: {complaint.notes or "нет"}
""".strip()


def _normalize_questions(value: object) -> list[str]:
    """Normalize doctor questions into a string list."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _serialize_comparison(payload: dict[str, object]) -> str:
    """Store structured comparison as JSON for the frontend."""
    structured = {
        "reply": str(payload.get("reply", "")).strip(),
        "agreements": str(payload.get("agreements", "")).strip(),
        "disagreements": str(payload.get("disagreements", "")).strip(),
        "recommendations": str(payload.get("recommendations", "")).strip(),
        "questions_for_doctor": _normalize_questions(
            payload.get("questions_for_doctor")
        ),
    }
    return json.dumps(structured, ensure_ascii=False)


def compare_opinions(
    complaint_id: int,
    doctor_feedback: str,
    user_id: str,
    settings: Settings | None = None,
) -> tuple[ComplaintRecord, OpinionComparisonResult]:
    """Compare assistant and doctor opinions for a saved complaint."""
    settings = settings or load_settings()
    cleaned_feedback = doctor_feedback.strip()

    if not cleaned_feedback:
        raise ValueError("Опишите мнение врача после очного визита.")

    complaint = _fetch_complaint(complaint_id, user_id)

    if not complaint.ai_diagnosis and not complaint.ai_analysis:
        raise ValueError(
            "Сначала нужно получить первое мнение ассистента в чате."
        )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE complaints
            SET doctor_feedback = %s
            WHERE id = %s AND user_id = %s
            """,
            (cleaned_feedback, complaint_id, user_id),
        )

    complaint = _fetch_complaint(complaint_id, user_id)

    if not settings.aitunnel_api_key:
        result = OpinionComparisonResult(
            ai_status="no_api_key",
            ai_opinion_comparison=(
                "Для сравнения мнений нужен AITUNNEL_API_KEY в локальном `.env`."
            ),
        )
        return complaint, result

    profile = _load_profile(user_id)
    labs = _load_recent_labs(user_id)
    user_prompt = _build_comparison_prompt(complaint, profile, labs)
    route = resolve_model_route(LlmTask.REVIEW, settings)

    try:
        completion = chat_completion(
            settings,
            LlmTask.REVIEW,
            messages=[
                ChatMessage(role="system", content=COMPARISON_SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_prompt),
            ],
            timeout=180.0,
            usage_context=UsageContext(
                user_id=user_id,
                operation_type="opinion_comparison",
                complaint_id=complaint_id,
                task=LlmTask.REVIEW,
            ),
        )
        payload = _extract_json(completion.content)
    except InsufficientCreditsError:
        raise
    except Exception as error:
        result = OpinionComparisonResult(
            ai_status="failed",
            ai_opinion_comparison=(
                f"Не удалось сравнить мнения ({route.model}): {error}"
            ),
        )
        return complaint, result

    comparison_text = _serialize_comparison(payload)
    result = OpinionComparisonResult(
        ai_status="completed",
        ai_opinion_comparison=comparison_text,
    )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE complaints
            SET ai_opinion_comparison = %s
            WHERE id = %s AND user_id = %s
            """,
            (comparison_text, complaint_id, user_id),
        )
        row = connection.execute(
            "SELECT * FROM complaints WHERE id = %s AND user_id = %s",
            (complaint_id, user_id),
        ).fetchone()

    return ComplaintRecord(**dict(row)), result
