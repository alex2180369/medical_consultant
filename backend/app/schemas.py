"""Pydantic schemas for API requests and responses."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Backend health response."""

    status: str
    app_name: str
    app_env: str


class UserPublic(BaseModel):
    """Public user data returned to the client."""

    id: str
    email: str
    name: str


class SessionInfo(BaseModel):
    """Current authenticated session."""

    user: UserPublic


class AccountDeleteRequest(BaseModel):
    """Confirm permanent account deletion."""

    confirm: bool = False


class MedicalProfile(BaseModel):
    """Personal medical profile collected during first intake."""

    model_config = ConfigDict(extra="ignore")

    full_name: str = ""
    age: int | None = Field(default=None, ge=0, le=130)
    birth_date: date | None = None
    sex: str = ""
    blood_type: str = ""
    height_cm: float | None = Field(default=None, ge=30, le=260)
    weight_kg: float | None = Field(default=None, ge=1, le=500)
    diabetes_status: str = ""
    cardiovascular_status: str = ""
    chronic_conditions: str = ""
    allergies: str = ""
    medications: str = ""
    family_history: str = ""
    lifestyle: str = ""
    activity_level: str = ""
    smoking_status: str = ""
    sleep_hours: int | None = Field(default=None, ge=0, le=24)
    stress_level: str = ""
    family_members: int | None = Field(default=None, ge=1, le=20)
    notes: str = ""
    updated_at: datetime | None = None


class LabResultCreate(BaseModel):
    """Laboratory marker submitted by the user."""

    marker_name: str = Field(min_length=1, max_length=120)
    value: float
    unit: str = ""
    reference_range: str = ""
    measured_at: date
    comment: str = ""


class LabTrend(BaseModel):
    """Simple comparison with a previous marker value."""

    previous_value: float | None
    delta: float | None
    direction: str


class LabResult(LabResultCreate):
    """Stored laboratory marker with trend information."""

    id: int
    created_at: datetime
    trend: LabTrend | None = None


class DocumentRecord(BaseModel):
    """Stored medical document metadata."""

    id: int
    filename: str
    content_type: str
    path: str
    description: str
    extracted_text: str = ""
    analysis_status: str = "pending"
    created_at: datetime


class ComplaintCreate(BaseModel):
    """Symptoms, complaints, and physician feedback from a user entry."""

    symptoms: str = Field(default="", max_length=4000)
    doctor_feedback: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=4000)
    occurred_at: date
    analysis_mode: Literal["standard", "complex", "review"] = "standard"


class ComplaintRecord(ComplaintCreate):
    """Stored complaint entry with optional AI analysis."""

    id: int
    created_at: datetime
    ai_analysis: str = ""
    ai_diagnosis: str = ""
    ai_treatment: str = ""
    ai_doctor_questions: str = ""
    ai_urgency: str = ""
    ai_status: str = "pending"
    ai_opinion_comparison: str = ""


class OpinionCompareRequest(BaseModel):
    """Doctor opinion after an in-person visit."""

    doctor_feedback: str = Field(min_length=1, max_length=4000)


class ConsultationChatRequest(BaseModel):
    """Next message in a first-opinion consultation chat."""

    consultation_id: int | None = None
    message: str = Field(min_length=1, max_length=4000)
    occurred_at: date | None = None
    doctor_feedback: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=4000)
    force_complex: bool = False


class ConsultationChatResponse(BaseModel):
    """Assistant reply for one consultation turn."""

    consultation_id: int
    reply: str
    phase: Literal["anamnesis", "conclusion"]
    ai_status: str
    complaint: ComplaintRecord | None = None


class NutritionPlanRequest(BaseModel):
    """Request for generating a weekly nutrition plan."""

    pantry_items: list[str] = Field(default_factory=list)
    include_medical_recommendations: bool = False


class NutritionPlanResponse(BaseModel):
    """Generated weekly nutrition plan."""

    ai_status: str
    message: str = ""
    menu: list[dict[str, object]] = Field(default_factory=list)
