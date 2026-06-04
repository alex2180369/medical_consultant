"""Authentication and family user management routes."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.schemas import (
    LoginRequest,
    LoginResponse,
    SessionInfo,
    UserCreate,
    UserPublic,
)
from app.services.auth_service import (
    SESSION_COOKIE,
    AuthContext,
    authenticate_user,
    clear_session_cookie,
    create_session,
    create_user,
    delete_session,
    get_auth_context,
    get_user_by_id,
    list_active_users,
    require_admin,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_public(user) -> UserPublic:
    return UserPublic(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response) -> LoginResponse:
    """Authenticate a family member or administrator."""
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль.",
        )

    token = create_session(user.id)
    set_session_cookie(response, token)

    return LoginResponse(
        user=_to_public(user),
        effective_user=_to_public(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    _: Annotated[AuthContext, Depends(get_auth_context)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    """End the current session."""
    delete_session(session_token)
    clear_session_cookie(response)


@router.get("/me", response_model=SessionInfo)
def current_session(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> SessionInfo:
    """Return the authenticated user and effective profile scope."""
    effective_user = get_user_by_id(auth.effective_user_id) or auth.user

    return SessionInfo(
        user=_to_public(auth.user),
        effective_user=_to_public(effective_user),
        is_admin=auth.user.role == "admin",
    )


@router.get("/users", response_model=list[UserPublic])
def list_users(
    _: Annotated[AuthContext, Depends(require_admin)],
) -> list[UserPublic]:
    """Return family users for the admin selector."""
    return [_to_public(user) for user in list_active_users()]


@router.post("/users", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def create_family_user(
    payload: UserCreate,
    _: Annotated[AuthContext, Depends(require_admin)],
) -> UserPublic:
    """Create a new family member account."""
    try:
        user = create_user(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role="member",
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return _to_public(user)
