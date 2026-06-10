"""Multi-turn consultation chat for the assistant's first medical opinion."""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.config import Settings, load_settings
from app.database import get_connection
from app.schemas import ComplaintCreate, ComplaintRecord, MedicalProfile
from app.services.document_analyzer import format_documents_for_context
from app.services.llm_client import ChatMessage, chat_completion
from app.services.llm_router import LlmTask, resolve_model_route
from app.services.symptom_analyzer import (
    SymptomAnalysisResult,
    _fetch_medication_notes,
    _format_list,
    _load_profile,
    _load_recent_labs,
    _needs_medication_review,
    resolve_symptom_task,
)

ConsultationPhase = Literal["anamnesis", "conclusion"]
MAX_USER_TURNS = 8

CONSULTATION_SYSTEM_PROMPT = """
Ты медицинский информационный ассистент для личного использования в РФ.
Сценарий: ПЕРВОЕ мнение ДО визита пациента к врачу.

Пациент ещё не был у врача (или только планирует визит). Твоя задача в диалоге:
1) собрать анамнез уточняющими вопросами (по 1–2 за раз);
2) когда данных достаточно — дать первое мнение: ориентировочный диагноз(ы),
   план лечения/тактики и вопросы, которые стоит задать врачу на приёме.

Правила:
- Не спрашивай, что сказал врач — пациент к врачу ещё не ходил.
- Уточняй: симптомы, когда началось, динамика, интенсивность, триггеры,
  сопутствующие симптомы, препараты, аллергии, хронические болезни.
- Учитывай профиль пациента и анализы из контекста.
- Учитывай загруженные документы (анализы, PDF, снимки) из контекста.
- На этапе conclusion сформулируй первое мнение простым языком.
- Если даёшь рекомендации по питанию или ограничениям рациона, в конце спроси:
  "Разрешаете учесть эти рекомендации в ИИ-нутрициологе при обновлении меню%s"
- Это информационная поддержка, не замена очного приёма.
- При признаках экстренности — явно рекомендуй срочную помощь.
- Пиши на русском.

Когда переходить к conclusion:
- обычно после 3–6 ответов пациента;
- если пользователь просит итог/диагноз/лечение;
- если достигнут лимит сообщений.

Ответ верни строго в JSON без markdown-обёртки:
{
  "phase": "anamnesis|conclusion",
  "reply": "сообщение ассистента пользователю",
  "anamnesis_summary": "краткое резюме собранного анамнеза или пустая строка",
  "diagnoses": ["гипотеза 1", "гипотеза 2"],
  "treatment_plan": "рекомендуемый план лечения и тактика",
  "doctor_questions": ["что спросить у врача на приёме"],
  "urgency": "routine|soon|urgent",
  "summary": "краткое резюме первого мнения"
}

На этапе anamnesis поля diagnoses, treatment_plan, doctor_questions,
urgency, summary могут быть пустыми.
""".strip()


@dataclass(frozen=True, slots=True)
class StoredMessage:
    """Persisted consultation message."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ConsultationTurnResult:
    """Result of one chat turn."""

    consultation_id: int
    reply: str
    phase: ConsultationPhase
    ai_status: str
    complaint: ComplaintRecord | None = None


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


def _create_consultation(
    user_id: str,
    occurred_at: date,
    doctor_feedback: str,
    notes: str,
) -> int:
    """Create a new active consultation session."""
    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO consultations (
                user_id,
                occurred_at,
                doctor_feedback,
                notes,
                status
            )
            VALUES (%s, %s, %s, %s, 'active')
            RETURNING id
            """,
            (user_id, occurred_at, doctor_feedback, notes),
        ).fetchone()
        return int(row["id"])


def _load_consultation_meta(consultation_id: int, user_id: str) -> dict[str, str]:
    """Load consultation metadata."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM consultations WHERE id = %s AND user_id = %s",
            (consultation_id, user_id),
        ).fetchone()

    if row is None:
        raise ValueError("Consultation not found.")

    if row["status"] != "active":
        raise ValueError("Consultation is already completed.")

    return dict(row)


def _load_messages(consultation_id: int) -> list[StoredMessage]:
    """Load consultation messages in chronological order."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT role, content
            FROM consultation_messages
            WHERE consultation_id = %s
            ORDER BY id ASC
            """,
            (consultation_id,),
        ).fetchall()

    return [StoredMessage(role=row["role"], content=row["content"]) for row in rows]


def _save_message(consultation_id: int, role: str, content: str) -> None:
    """Persist one consultation message."""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO consultation_messages (consultation_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (consultation_id, role, content),
        )


def _build_context_block(
    profile: MedicalProfile,
    labs: list[str],
    doctor_feedback: str,
    notes: str,
    user_turns: int,
    user_id: str,
) -> str:
    """Build static context for the consultation prompt."""
    lab_block = "\n".join(f"- {item}" for item in labs) if labs else "Нет данных."
    documents_block = format_documents_for_context(user_id)
    force_conclusion = user_turns >= MAX_USER_TURNS
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
Контекст консультации:
- Ответов пациента в этом диалоге: {user_turns}
- Лимит до принудительного итога: {MAX_USER_TURNS}
- Принудительно перейти к conclusion: {"да" if force_conclusion else "нет"}

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

Обратная связь от врача: {
        doctor_feedback or "ещё не получена — пациент к врачу не ходил"
    }
Наблюдения пациента: {notes or "нет"}

Последние анализы:
{lab_block}

Загруженные документы (анализы, снимки, PDF):
{documents_block}
""".strip()


def _compile_symptoms(messages: list[StoredMessage]) -> str:
    """Join user messages into a single anamnesis text."""
    user_parts = [
        message.content.strip()
        for message in messages
        if message.role == "user"
    ]
    return "\n\n".join(part for part in user_parts if part)


def _build_analysis_from_payload(payload: dict[str, object]) -> SymptomAnalysisResult:
    """Convert consultation JSON into stored complaint analysis fields."""
    diagnoses = _format_list(payload.get("diagnoses"))
    treatment = str(payload.get("treatment_plan", "")).strip()
    doctor_questions = _format_list(payload.get("doctor_questions"))
    urgency = str(payload.get("urgency", "routine")).strip() or "routine"
    summary = str(payload.get("summary", "")).strip()
    anamnesis_summary = str(payload.get("anamnesis_summary", "")).strip()

    analysis_parts = [
        part
        for part in [summary, anamnesis_summary, diagnoses, treatment, doctor_questions]
        if part
    ]

    return SymptomAnalysisResult(
        ai_status="completed",
        ai_analysis="\n\n".join(analysis_parts),
        ai_diagnosis=diagnoses,
        ai_treatment=treatment,
        ai_doctor_questions=doctor_questions,
        ai_urgency=urgency,
    )


def _resolve_consultation_task(
    force_complex: bool,
    complaint: ComplaintCreate,
    profile: MedicalProfile,
    user_turns: int,
) -> LlmTask:
    """Pick a model for the current consultation turn."""
    if user_turns < MAX_USER_TURNS:
        return LlmTask.SYMPTOMS

    analysis_mode = "complex" if force_complex else "standard"
    return resolve_symptom_task(analysis_mode, complaint, profile)


def _save_complaint_from_consultation(
    user_id: str,
    consultation_id: int,
    occurred_at: date,
    doctor_feedback: str,
    notes: str,
    symptoms: str,
    analysis: SymptomAnalysisResult,
) -> ComplaintRecord:
    """Persist a completed consultation as a complaint record."""
    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO complaints (
                user_id,
                symptoms,
                doctor_feedback,
                notes,
                occurred_at,
                ai_analysis,
                ai_diagnosis,
                ai_treatment,
                ai_doctor_questions,
                ai_urgency,
                ai_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                symptoms,
                doctor_feedback,
                notes,
                occurred_at,
                analysis.ai_analysis,
                analysis.ai_diagnosis,
                analysis.ai_treatment,
                analysis.ai_doctor_questions,
                analysis.ai_urgency,
                analysis.ai_status,
            ),
        ).fetchone()
        complaint_id = int(row["id"])
        connection.execute(
            """
            UPDATE consultations
            SET status = 'completed', complaint_id = %s
            WHERE id = %s AND user_id = %s
            """,
            (complaint_id, consultation_id, user_id),
        )
        row = connection.execute(
            "SELECT * FROM complaints WHERE id = %s AND user_id = %s",
            (complaint_id, user_id),
        ).fetchone()

    return ComplaintRecord(**dict(row))


def continue_consultation(
    *,
    message: str,
    user_id: str,
    consultation_id: int | None = None,
    occurred_at: date | None = None,
    doctor_feedback: str = "",
    notes: str = "",
    force_complex: bool = False,
    settings: Settings | None = None,
) -> ConsultationTurnResult:
    """Process the next user message in a first-opinion consultation."""
    settings = settings or load_settings()
    cleaned_message = message.strip()

    if not cleaned_message:
        raise ValueError("Message must not be empty.")

    if consultation_id is None:
        if occurred_at is None:
            raise ValueError("occurred_at is required for a new consultation.")
        consultation_id = _create_consultation(user_id, occurred_at, "", notes)
    else:
        _load_consultation_meta(consultation_id, user_id)

    from app.services.pii_filter import PII_WARNING, detect_sensitive_data

    pii_result = detect_sensitive_data(cleaned_message)
    if pii_result.contains_pii:
        return ConsultationTurnResult(
            consultation_id=consultation_id,
            reply=PII_WARNING,
            phase="anamnesis",
            ai_status="pii_blocked",
        )

    _save_message(consultation_id, "user", cleaned_message)

    if not settings.aitunnel_api_key:
        reply = (
            "Для консультации нужен ключ AITUNNEL_API_KEY в локальном `.env`. "
            "Сообщение сохранено, но ответ ассистента не сформирован."
        )
        _save_message(consultation_id, "assistant", reply)
        return ConsultationTurnResult(
            consultation_id=consultation_id,
            reply=reply,
            phase="anamnesis",
            ai_status="no_api_key",
        )

    meta = _load_consultation_meta(consultation_id, user_id)
    messages = _load_messages(consultation_id)
    profile = _load_profile(user_id)
    labs = _load_recent_labs(user_id)
    user_turns = sum(1 for item in messages if item.role == "user")
    occurred_value = meta["occurred_at"]
    occurred = (
        occurred_value
        if isinstance(occurred_value, date)
        else date.fromisoformat(str(occurred_value))
    )

    complaint = ComplaintCreate(
        symptoms=_compile_symptoms(messages),
        doctor_feedback=meta["doctor_feedback"],
        notes=meta["notes"],
        occurred_at=occurred,
    )

    context_block = _build_context_block(
        profile,
        labs,
        meta["doctor_feedback"],
        meta["notes"],
        user_turns,
        user_id,
    )

    llm_messages = [
        ChatMessage(role="system", content=CONSULTATION_SYSTEM_PROMPT),
        ChatMessage(role="user", content=context_block),
    ]
    for stored in messages:
        llm_messages.append(
            ChatMessage(role=stored.role, content=stored.content)
        )

    task = _resolve_consultation_task(
        force_complex,
        complaint,
        profile,
        user_turns,
    )
    route = resolve_model_route(task, settings)
    timeout = 180.0 if task != LlmTask.SYMPTOMS else 120.0

    try:
        completion = chat_completion(
            settings,
            task,
            messages=llm_messages,
            timeout=timeout,
        )
        payload = _extract_json(completion.content)
    except Exception as error:
        reply = (
            f"Не удалось получить ответ от модели ({route.model}): {error}. "
            "Попробуйте переформулировать сообщение."
        )
        _save_message(consultation_id, "assistant", reply)
        return ConsultationTurnResult(
            consultation_id=consultation_id,
            reply=reply,
            phase="anamnesis",
            ai_status="failed",
        )

    reply = str(payload.get("reply", "")).strip()
    if not reply:
        reply = "Пожалуйста, уточните симптомы или ответьте на предыдущий вопрос."

    phase_raw = str(payload.get("phase", "anamnesis")).strip().lower()
    phase: ConsultationPhase = (
        "conclusion" if phase_raw == "conclusion" else "anamnesis"
    )

    if user_turns >= MAX_USER_TURNS:
        phase = "conclusion"

    _save_message(consultation_id, "assistant", reply)

    if phase == "anamnesis":
        return ConsultationTurnResult(
            consultation_id=consultation_id,
            reply=reply,
            phase="anamnesis",
            ai_status="completed",
        )

    analysis = _build_analysis_from_payload(payload)
    if _needs_medication_review(complaint, profile):
        medication_notes = _fetch_medication_notes(
            settings,
            complaint,
            profile,
            labs,
        )
        if medication_notes:
            medication_block = f"Комментарий по препаратам:\n{medication_notes}"
            analysis = SymptomAnalysisResult(
                ai_status=analysis.ai_status,
                ai_analysis=f"{analysis.ai_analysis}\n\n{medication_block}".strip(),
                ai_diagnosis=analysis.ai_diagnosis,
                ai_treatment=f"{analysis.ai_treatment}\n\n{medication_block}".strip(),
                ai_doctor_questions=analysis.ai_doctor_questions,
                ai_urgency=analysis.ai_urgency,
            )

    complaint_record = _save_complaint_from_consultation(
        user_id,
        consultation_id,
        occurred,
        "",
        meta["notes"],
        complaint.symptoms,
        analysis,
    )

    return ConsultationTurnResult(
        consultation_id=consultation_id,
        reply=reply,
        phase="conclusion",
        ai_status=analysis.ai_status,
        complaint=complaint_record,
    )
