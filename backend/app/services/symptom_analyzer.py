"""AI analysis of symptoms and complaints."""

import json
import re
from dataclasses import dataclass
from typing import Literal

from app.config import Settings, load_settings
from app.database import get_connection
from app.schemas import ComplaintCreate, MedicalProfile
from app.services.llm_client import ChatMessage, chat_completion
from app.services.llm_router import LlmTask, resolve_model_route

AnalysisMode = Literal["standard", "complex", "review"]

SYSTEM_PROMPT = """
Ты медицинский информационный ассистент для личного использования в РФ.
Ты НЕ врач, НЕ ставишь окончательный диагноз и НЕ назначаешь лечение.
Твоя задача — помочь человеку подготовиться к очному приёму.

Правила:
1. Формулируй только ОРИЕНТИРОВОЧНЫЕ гипотезы и вероятные причины.
2. Предлагай только ПРИМЕРНЫЙ подход: что обсудить с врачом, какие обследования
   могут понадобиться, общие принципы поддержки.
3. Не назначай конкретные дозировки и схемы препаратов без врача.
4. Учитывай возраст, пол, хронические заболевания, аллергии и текущие препараты.
5. Если есть признаки экстренности — явно укажи срочное обращение за помощью.
6. Пиши простым человеческим языком на русском.

Ответ верни строго в JSON без markdown-обёртки:
{
  "diagnoses": ["гипотеза 1", "гипотеза 2"],
  "treatment_notes": "примерный подход и что обсудить с врачом",
  "doctor_questions": ["вопрос 1", "вопрос 2"],
  "urgency": "routine|soon|urgent",
  "summary": "краткое резюме для пользователя"
}
""".strip()

MEDICATIONS_PROMPT = """
Ты медицинский информационный ассистент для личного использования в РФ.
Ты НЕ врач и НЕ меняешь назначения.

Проанализируй текущие препараты пациента в контексте жалобы.
Укажи возможные взаимодействия, побочные эффекты, на что обратить внимание
и какие вопросы задать врачу или фармацевту. Не назначай новые препараты.

Ответ верни строго в JSON без markdown-обёртки:
{
  "medication_notes": "краткий информационный комментарий по препаратам"
}
""".strip()

COMPLEX_HINT = """
Это сложное или многосимптомное обращение. Рассуждай пошагово, сравни несколько
гипотез и явно отметь, что требует срочной очной помощи.
""".strip()

REVIEW_HINT = """
Это углублённый повторный разбор сохранённого обращения. Дай более детальную
оценку, уточни дифференциальный ряд и подготовь расширенный список вопросов врачу.
""".strip()

COMPLEX_KEYWORDS = (
    "сильн",
    "остр",
    "кров",
    "одыш",
    "груд",
    "сердц",
    "сознан",
    "температур",
    "не проходит",
    "ухудш",
    "онемен",
    "слабость",
    "рвот",
    "обморок",
)


@dataclass(frozen=True, slots=True)
class SymptomAnalysisResult:
    """Structured AI response for a complaint."""

    ai_status: str
    ai_analysis: str
    ai_diagnosis: str
    ai_treatment: str
    ai_doctor_questions: str
    ai_urgency: str


def _load_profile(user_id: int) -> MedicalProfile:
    """Load the stored medical profile."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if row is None:
        return MedicalProfile()

    return MedicalProfile(**dict(row))


def _load_recent_labs(user_id: int, limit: int = 8) -> list[str]:
    """Load recent laboratory markers for context."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT marker_name, value, unit, measured_at
            FROM lab_results
            WHERE user_id = ?
            ORDER BY measured_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    return [
        f"{row['marker_name']}: {row['value']} {row['unit']} ({row['measured_at']})"
        for row in rows
    ]


def _build_user_prompt(
    complaint: ComplaintCreate,
    profile: MedicalProfile,
    labs: list[str],
    *,
    extra_instruction: str = "",
) -> str:
    """Build the user prompt with profile and complaint context."""
    bmi = ""
    if profile.height_cm and profile.weight_kg and profile.height_cm > 0:
        height_m = profile.height_cm / 100
        bmi_value = profile.weight_kg / (height_m * height_m)
        bmi = f"{bmi_value:.1f}"
    sleep_text = (
        str(profile.sleep_hours)
        if profile.sleep_hours is not None
        else "нет данных"
    )

    lab_block = "\n".join(f"- {item}" for item in labs) if labs else "Нет данных."
    instruction_block = (
        f"\n\nДополнительная инструкция:\n{extra_instruction}"
        if extra_instruction
        else ""
    )

    return f"""
Профиль пациента:
- Имя: {profile.full_name or "не указано"}
- Возраст: {profile.age if profile.age is not None else "не указан"}
- Дата рождения: {profile.birth_date or "не указана"}
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
- Семейная история: {profile.family_history or "нет данных"}
- Образ жизни: {profile.lifestyle or "нет данных"}
- Физическая активность: {profile.activity_level or "нет данных"}
- Курение: {profile.smoking_status or "нет данных"}
- Сон: {sleep_text} ч/сутки
- Стресс: {profile.stress_level or "нет данных"}

Последние анализы:
{lab_block}

Жалоба от {complaint.occurred_at.isoformat()}:
- Симптомы: {complaint.symptoms}
- Обратная связь от врачей: {complaint.doctor_feedback or "нет"}
- Наблюдения: {complaint.notes or "нет"}{instruction_block}
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


def _format_list(value: object) -> str:
    """Convert a list-like value to readable text."""
    if isinstance(value, list):
        return "\n".join(f"• {item}" for item in value if str(item).strip())
    if isinstance(value, str):
        return value.strip()
    return ""


def _mentions_medications(complaint: ComplaintCreate) -> bool:
    """Return True when the complaint text likely mentions medications."""
    text = " ".join(
        part
        for part in (complaint.symptoms, complaint.notes, complaint.doctor_feedback)
        if part
    ).lower()
    markers = ("препарат", "лекарств", "таблет", "капсул", "мг ", "назнач")
    return any(marker in text for marker in markers)


def _should_use_complex_analysis(
    complaint: ComplaintCreate,
    profile: MedicalProfile,
) -> bool:
    """Heuristically detect complaints that benefit from a reasoning model."""
    text = f"{complaint.symptoms} {complaint.notes}".lower()

    if len(complaint.symptoms) >= 350:
        return True

    if profile.chronic_conditions.strip() and len(complaint.symptoms) >= 120:
        return True

    if sum(keyword in text for keyword in COMPLEX_KEYWORDS) >= 2:
        return True

    symptom_parts = re.split(r"[,;\n]|(?:\s+и\s+)", complaint.symptoms)
    if len([part for part in symptom_parts if part.strip()]) >= 4:
        return True

    return False


def resolve_symptom_task(
    analysis_mode: AnalysisMode,
    complaint: ComplaintCreate,
    profile: MedicalProfile,
) -> LlmTask:
    """Choose the LLM task for a complaint analysis request."""
    if analysis_mode == "review":
        return LlmTask.REVIEW
    if analysis_mode == "complex":
        return LlmTask.COMPLEX_SYMPTOMS
    if _should_use_complex_analysis(complaint, profile):
        return LlmTask.COMPLEX_SYMPTOMS
    return LlmTask.SYMPTOMS


def _task_instruction(task: LlmTask) -> str:
    """Return extra prompt guidance for specialized analysis tasks."""
    if task == LlmTask.COMPLEX_SYMPTOMS:
        return COMPLEX_HINT
    if task == LlmTask.REVIEW:
        return REVIEW_HINT
    return ""


def _needs_medication_review(
    complaint: ComplaintCreate,
    profile: MedicalProfile,
) -> bool:
    """Return True when a medication-focused model should run."""
    return bool(profile.medications.strip()) or _mentions_medications(complaint)


def _fetch_medication_notes(
    settings: Settings,
    complaint: ComplaintCreate,
    profile: MedicalProfile,
    labs: list[str],
) -> str:
    """Ask the medications model for interaction and safety notes."""
    if not _needs_medication_review(complaint, profile):
        return ""

    user_prompt = _build_user_prompt(complaint, profile, labs)
    try:
        completion = chat_completion(
            settings,
            LlmTask.MEDICATIONS,
            messages=[
                ChatMessage(role="system", content=MEDICATIONS_PROMPT),
                ChatMessage(role="user", content=user_prompt),
            ],
        )
        payload = _extract_json(completion.content)
    except Exception:
        return ""

    return str(payload.get("medication_notes", "")).strip()


def analyze_complaint(
    complaint: ComplaintCreate,
    settings: Settings | None = None,
    *,
    analysis_mode: AnalysisMode = "standard",
    user_id: int = 1,
) -> SymptomAnalysisResult:
    """Analyze a complaint and return orientational medical guidance."""
    settings = settings or load_settings()
    profile = _load_profile(user_id)
    task = resolve_symptom_task(analysis_mode, complaint, profile)
    route = resolve_model_route(task, settings)

    if not settings.aitunnel_api_key:
        return SymptomAnalysisResult(
            ai_status="no_api_key",
            ai_analysis=(
                "Для анализа жалоб нужен ключ AITUNNEL_API_KEY в локальном `.env`. "
                "Жалоба сохранена, но ИИ-оценка не выполнена."
            ),
            ai_diagnosis="",
            ai_treatment="",
            ai_doctor_questions="",
            ai_urgency="",
        )

    labs = _load_recent_labs(user_id)
    user_prompt = _build_user_prompt(
        complaint,
        profile,
        labs,
        extra_instruction=_task_instruction(task),
    )
    timeout = 180.0 if task in {LlmTask.COMPLEX_SYMPTOMS, LlmTask.REVIEW} else 120.0

    try:
        completion = chat_completion(
            settings,
            task,
            messages=[
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=user_prompt),
            ],
            timeout=timeout,
        )
        payload = _extract_json(completion.content)
    except Exception as error:
        return SymptomAnalysisResult(
            ai_status="failed",
            ai_analysis=(
                f"Не удалось получить оценку от модели ({route.model}): {error}"
            ),
            ai_diagnosis="",
            ai_treatment="",
            ai_doctor_questions="",
            ai_urgency="",
        )

    diagnoses = _format_list(payload.get("diagnoses"))
    treatment = str(payload.get("treatment_notes", "")).strip()
    doctor_questions = _format_list(payload.get("doctor_questions"))
    urgency = str(payload.get("urgency", "routine")).strip() or "routine"
    summary = str(payload.get("summary", "")).strip()

    medication_notes = _fetch_medication_notes(settings, complaint, profile, labs)
    if medication_notes:
        medication_block = f"Комментарий по препаратам:\n{medication_notes}"
        treatment = (
            f"{treatment}\n\n{medication_block}".strip()
            if treatment
            else medication_block
        )

    analysis_parts = [
        part for part in [summary, diagnoses, treatment, doctor_questions] if part
    ]
    ai_analysis = "\n\n".join(analysis_parts)

    return SymptomAnalysisResult(
        ai_status="completed",
        ai_analysis=ai_analysis,
        ai_diagnosis=diagnoses,
        ai_treatment=treatment,
        ai_doctor_questions=doctor_questions,
        ai_urgency=urgency,
    )
