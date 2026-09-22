"""Email/password authentication routes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.config import load_settings
from app.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SessionInfo,
    UserPublic,
)
from app.services.admin_notifier import notify_admin_new_application
from app.services.auth_service import (
    AuthContext,
    create_access_token,
    ensure_user_is_approved,
    generate_reset_token,
    get_auth_context,
    hash_password,
    verify_password,
)
from app.services.email_service import send_password_reset_email, smtp_configured
from app.services.registration_enrichment import enrich_registration
from app.services.user_service import (
    RESET_TOKEN_TTL,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_reset_token,
    is_password_reset_rate_limited,
    record_password_reset_request,
    save_registration_enrichment,
    set_password_reset_token,
    update_user_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

FORGOT_PASSWORD_MESSAGE = (
    "Если аккаунт существует, письмо для восстановления пароля отправлено."
)
REGISTER_PENDING_MESSAGE = (
    "Заявка на регистрацию отправлена. "
    "Ожидайте подтверждения администратора."
)


def _to_public(auth: AuthContext) -> UserPublic:
    return UserPublic(
        id=auth.user_id,
        email=auth.email,
        name=auth.name,
    )


def _auth_response(user: dict[str, object]) -> AuthResponse:
    token = create_access_token(
        user_id=str(user["id"]),
        email=str(user["email"]),
        name=str(user["display_name"]),
    )
    return AuthResponse(
        access_token=token,
        user=UserPublic(
            id=str(user["id"]),
            email=str(user["email"]),
            name=str(user["display_name"]),
        ),
    )


def _process_new_application(user_id: str) -> None:
    user = get_user_by_id(user_id)
    if user is None or user["status"] != "pending":
        return

    enrichment = enrich_registration(
        email=str(user["email"]),
        display_name=str(user["display_name"]),
        user_id=user_id,
    )
    save_registration_enrichment(
        user_id,
        suggested_name=enrichment.suggested_name,
        analysis=(
            f"{enrichment.analysis}\n\nРекомендация: {enrichment.recommendation}"
        ),
        confidence=enrichment.confidence,
    )

    refreshed = get_user_by_id(user_id)
    if refreshed is None:
        return

    notify_payload = {
        **refreshed,
        "recommendation": enrichment.recommendation,
    }
    notify_admin_new_application(notify_payload)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
) -> RegisterResponse:
    """Create a registration application for admin approval."""
    if not payload.consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо дать согласие на обработку персональных данных.",
        )

    user = create_user(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.name,
        consent_accepted_at=datetime.now(UTC),
    )

    settings = load_settings()
    if settings.app_env == "test":
        return RegisterResponse(message="Регистрация завершена.")

    background_tasks.add_task(_process_new_application, user["id"])
    return RegisterResponse(message=REGISTER_PENDING_MESSAGE)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    """Authenticate an approved user and return a JWT."""
    user = get_user_by_email(payload.email)
    if user is None or not verify_password(
        payload.password, str(user["password_hash"])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль.",
        )

    ensure_user_is_approved(user)
    return _auth_response(user)


@router.get("/me", response_model=SessionInfo)
def current_session(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> SessionInfo:
    """Return the authenticated user."""
    return SessionInfo(user=_to_public(auth))


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest) -> MessageResponse:
    """Send a password reset link when SMTP is configured."""
    if not smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Восстановление пароля временно недоступно.",
        )

    if is_password_reset_rate_limited(payload.email):
        return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)

    record_password_reset_request(payload.email)

    user = get_user_by_email(payload.email)
    if user is not None and user["status"] == "approved":
        settings = load_settings()
        token = generate_reset_token()
        expires_at = datetime.now(UTC) + RESET_TOKEN_TTL
        set_password_reset_token(str(user["id"]), token, expires_at)
        reset_url = f"{settings.frontend_url.rstrip('/')}/?reset={token}"
        send_password_reset_email(recipient=str(user["email"]), reset_url=reset_url)

    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest) -> MessageResponse:
    """Set a new password using a one-time reset token."""
    user = get_user_by_reset_token(payload.token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка для восстановления недействительна или устарела.",
        )

    update_user_password(str(user["id"]), hash_password(payload.password))
    return MessageResponse(message="Пароль успешно обновлён.")
