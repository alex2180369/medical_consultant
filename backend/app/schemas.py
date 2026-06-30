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


class RegisterResponse(BaseModel):
    """Registration application accepted for moderation."""

    message: str


class RejectUserRequest(BaseModel):
    """Reject a pending registration application."""

    reason: str = ""


class AdminUserRecord(BaseModel):
    """User record visible in the admin panel."""

    id: str
    email: str
    name: str
    status: str
    role: str
    ai_suggested_name: str = ""
    ai_email_analysis: str = ""
    ai_confidence: str = ""
    ai_analyzed_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str = ""
    created_at: datetime | None = None


class BlockedEmailRecord(BaseModel):
    """Permanently blocked email address."""

    email: str
    reason: str
    blocked_at: datetime
    blocked_by: str = ""


class AuthResponse(BaseModel):
    """Successful login or registration response."""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class RegisterRequest(BaseModel):
    """Register a new user account."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    consent: bool = False


class LoginRequest(BaseModel):
    """Authenticate with email and password."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    """Request a password reset email."""

    email: str = Field(min_length=3, max_length=320)


class ResetPasswordRequest(BaseModel):
    """Set a new password using a reset token."""

    token: str = Field(min_length=16, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    """Simple status message."""

    message: str


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


class TurnUsageInfo(BaseModel):
    """Billing details for one consultation turn."""

    credits_charged: int
    estimated_credits: int
    tokens_total: int
    model: str
    balance_remaining: int
    free_turns_remaining: int
    used_free_turn: bool = False


class ConsultationChatResponse(BaseModel):
    """Assistant reply for one consultation turn."""

    consultation_id: int
    reply: str
    phase: Literal["anamnesis", "conclusion"]
    ai_status: str
    complaint: ComplaintRecord | None = None
    usage: TurnUsageInfo | None = None


class WalletResponse(BaseModel):
    """Current wallet balance for the authenticated user."""

    credits_balance: int
    free_turns_remaining: int
    credits_per_rub: int
    starter_credits: int = 100
    payment_gateway_status: str = "coming_soon"


class TopUpPackageResponse(BaseModel):
    """Wallet top-up package available for online payment."""

    id: str
    credits: int
    amount_rub: float
    title: str


class PaymentPackagesResponse(BaseModel):
    """Available payment packages and gateway status."""

    payment_gateway_status: str
    credits_per_rub: int
    packages: list[TopUpPackageResponse]


class CreatePaymentRequest(BaseModel):
    """Request to create an online payment."""

    package_id: str = Field(min_length=1, max_length=64)


class PaymentOrderResponse(BaseModel):
    """Payment order state for the authenticated user."""

    id: str
    package_id: str
    amount_rub: float
    credits: int
    status: str
    provider: str
    confirmation_url: str | None = None
    created_at: datetime
    updated_at: datetime
    paid_at: datetime | None = None


class WalletTransactionResponse(BaseModel):
    """Wallet transaction visible to the user."""

    id: int
    delta_credits: int
    reason: str
    reference_id: str | None = None
    created_at: datetime


class AdminTopUpRequest(BaseModel):
    """Manual wallet top-up by administrator."""

    credits: int = Field(gt=0, le=1_000_000)
    note: str = Field(default="", max_length=200)


class AdminWalletResponse(BaseModel):
    """Wallet state visible to administrator."""

    user_id: str
    credits_balance: int
    free_turns_remaining: int


class NutritionPlanRequest(BaseModel):
    """Request for generating a weekly nutrition plan."""

    pantry_items: list[str] = Field(default_factory=list)
    include_medical_recommendations: bool = False


class NutritionPlanResponse(BaseModel):
    """Generated weekly nutrition plan."""

    ai_status: str
    message: str = ""
    menu: list[dict[str, object]] = Field(default_factory=list)


class UsageEventResponse(BaseModel):
    """Single LLM usage event visible to the account owner."""

    id: int
    operation_type: str
    llm_task: str | None = None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_credits: int
    charged_credits: int
    cache_hit: bool
    is_charged: bool
    consultation_id: int | None = None
    complaint_id: int | None = None
    document_id: int | None = None
    created_at: datetime


class UsageSummaryResponse(BaseModel):
    """Aggregated LLM usage for the account."""

    total_events: int
    total_tokens: int
    total_estimated_credits: int
    total_charged_credits: int
    credits_per_rub: int
    by_operation: dict[str, int]
    billing_mode: str = "credits"
    note: str = (
        "Списание кредитов активно. При нулевом балансе доступны бесплатные ходы."
    )


class DocumentCostEstimateResponse(BaseModel):
    """Pre-flight credit estimate for a document upload."""

    estimated_credits: int
    requires_confirmation: bool
    is_billable: bool
    analysis_type: str
    warning_message: str | None = None
    page_count: int | None = None
    file_size_bytes: int
    model: str | None = None


class ReceiptLineResponse(BaseModel):
    """Aggregated usage line on a consultation receipt."""

    operation_type: str
    operation_label: str
    model: str
    event_count: int
    total_tokens: int
    estimated_credits: int
    charged_credits: int


class ConsultationReceiptResponse(BaseModel):
    """Usage receipt for one consultation session."""

    consultation_id: int
    occurred_at: date | None = None
    status: str
    complaint_id: int | None = None
    total_tokens: int
    total_estimated_credits: int
    total_charged_credits: int
    free_turns_used: int
    lines: list[ReceiptLineResponse]
    generated_at: datetime
