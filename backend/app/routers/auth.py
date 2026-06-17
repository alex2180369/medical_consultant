"""Email/password authentication routes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import load_settings
from app.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionInfo,
    UserPublic,
)
from app.services.auth_service import (
    AuthContext,
    create_access_token,
    generate_reset_token,
    get_auth_context,
    hash_password,
    verify_password,
)
from app.services.email_service import send_password_reset_email, smtp_configured
from app.services.user_service import (
    RESET_TOKEN_TTL,
    create_user,
    get_user_by_email,
    get_user_by_reset_token,
    is_password_reset_rate_limited,
    record_password_reset_request,
    set_password_reset_token,
    update_user_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

FORGOT_PASSWORD_MESSAGE = (
    "Если аккаунт существует, письмо для восстановления пароля отправлено."
)


def _to_public(auth: AuthContext) -> UserPublic:
    return UserPublic(
        id=auth.user_id,
        email=auth.email,
        name=auth.name,
    )


def _auth_response(user: dict[str, str]) -> AuthResponse:
    token = create_access_token(
        user_id=user["id"],
        email=user["email"],
        name=user["display_name"],
    )
    return AuthResponse(
        access_token=token,
        user=UserPublic(
            id=user["id"],
            email=user["email"],
            name=user["display_name"],
        ),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> AuthResponse:
    """Register a new user with email and password."""
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
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    """Authenticate a user and return a JWT."""
    user = get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль.",
        )

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
    if user is not None:
        settings = load_settings()
        token = generate_reset_token()
        expires_at = datetime.now(UTC) + RESET_TOKEN_TTL
        set_password_reset_token(user["id"], token, expires_at)
        reset_url = f"{settings.frontend_url.rstrip('/')}/?reset={token}"
        send_password_reset_email(recipient=user["email"], reset_url=reset_url)

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

    update_user_password(user["id"], hash_password(payload.password))
    return MessageResponse(message="Пароль успешно обновлён.")
