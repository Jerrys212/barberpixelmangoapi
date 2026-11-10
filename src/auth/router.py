import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request, status

from src.auth import service as auth_service
from src.auth.dependencies import ClientInfoDep, CurrentSessionId, OwnerUser
from src.auth.schemas import (
    EmailRequest,
    LoginRequest,
    PasswordResetConfirm,
    RefreshRequest,
    RegisterRequest,
    SessionOut,
    TokenPair,
    VerifyEmailRequest,
)
from src.database import SessionDep
from src.email.dependencies import EmailSenderDep
from src.rate_limit import AUTH_RATE_LIMIT, limiter
from src.users.models import User
from src.users.schemas import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_RATE_LIMIT)
async def register(
    request: Request,
    data: RegisterRequest,
    session: SessionDep,
    sender: EmailSenderDep,
    background_tasks: BackgroundTasks,
) -> User:
    user, email = await auth_service.register_customer(session, data)
    if email is not None:
        background_tasks.add_task(sender.send, email)
    return user


@router.post("/login", response_model=TokenPair)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(
    request: Request, data: LoginRequest, session: SessionDep, client: ClientInfoDep
) -> TokenPair:
    return await auth_service.login(session, data, client)


@router.post("/refresh", response_model=TokenPair)
async def refresh(data: RefreshRequest, session: SessionDep) -> TokenPair:
    return await auth_service.refresh(session, data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session_id: CurrentSessionId, session: SessionDep) -> None:
    await auth_service.logout(session, session_id)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_RATE_LIMIT)
async def verify_email(request: Request, data: VerifyEmailRequest, session: SessionDep) -> None:
    await auth_service.verify_email(session, data)


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(AUTH_RATE_LIMIT)
async def resend_email_verification(
    request: Request,
    data: EmailRequest,
    session: SessionDep,
    sender: EmailSenderDep,
    background_tasks: BackgroundTasks,
) -> None:
    email = await auth_service.resend_email_verification(session, data.email)
    if email is not None:
        background_tasks.add_task(sender.send, email)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(AUTH_RATE_LIMIT)
async def request_password_reset(
    request: Request,
    data: EmailRequest,
    session: SessionDep,
    sender: EmailSenderDep,
    background_tasks: BackgroundTasks,
) -> None:
    email = await auth_service.request_password_reset(session, data.email)
    if email is not None:
        background_tasks.add_task(sender.send, email)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_RATE_LIMIT)
async def confirm_password_reset(
    request: Request, data: PasswordResetConfirm, session: SessionDep
) -> None:
    await auth_service.confirm_password_reset(session, data)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    _: OwnerUser,
    session: SessionDep,
    user_id: uuid.UUID | None = None,
    active: Annotated[bool, Query()] = True,
) -> list[SessionOut]:
    return await auth_service.list_sessions(session, user_id=user_id, active_only=active)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID, owner: OwnerUser, session: SessionDep, client: ClientInfoDep
) -> None:
    await auth_service.revoke_session_as_owner(session, owner, session_id, client)


@router.delete("/users/{user_id}/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_sessions(
    user_id: uuid.UUID, owner: OwnerUser, session: SessionDep, client: ClientInfoDep
) -> None:
    await auth_service.revoke_user_sessions_as_owner(session, owner, user_id, client)
