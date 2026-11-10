import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import service as audit_service
from src.audit.models import AuditAction
from src.auth import security
from src.auth.config import get_auth_settings
from src.auth.exceptions import (
    InvalidCredentials,
    InvalidToken,
    OtpInvalid,
    SessionNotFound,
    SessionRevoked,
)
from src.auth.models import (
    EmailVerificationCode,
    PasswordResetCode,
    RefreshSession,
    RefreshToken,
    RevokedReason,
)
from src.auth.repository import OtpModel, OtpRepository, SessionRepository
from src.auth.schemas import (
    LoginRequest,
    OwnerCreate,
    PasswordResetConfirm,
    RegisterRequest,
    SessionOut,
    SessionUserOut,
    TokenPair,
    VerifyEmailRequest,
)
from src.auth.security import OtpPurpose
from src.email import templates
from src.email.sender import OutgoingEmail
from src.models import utc_now
from src.users.exceptions import (
    EmailAlreadyRegistered,
    OwnerAlreadyExists,
    OwnerNotFound,
    UserNotFound,
)
from src.users.models import User, UserRole
from src.users.repository import UserRepository

logger = logging.getLogger(__name__)

_OTP_MODELS: dict[OtpPurpose, OtpModel] = {
    OtpPurpose.EMAIL_VERIFICATION: EmailVerificationCode,
    OtpPurpose.PASSWORD_RESET: PasswordResetCode,
}


@dataclass(frozen=True)
class ClientInfo:
    user_agent: str | None
    ip_address: str | None


async def register_customer(
    session: AsyncSession, data: RegisterRequest
) -> tuple[User, OutgoingEmail | None]:
    users = UserRepository(session)
    if await users.get_by_email(data.email):
        raise EmailAlreadyRegistered()
    user = await users.create(
        email=data.email,
        hashed_password=security.hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role=UserRole.CUSTOMER,
    )
    email = await _issue_otp(session, user, OtpPurpose.EMAIL_VERIFICATION, enforce_limits=False)
    return user, email


async def login(session: AsyncSession, data: LoginRequest, client: ClientInfo) -> TokenPair:
    settings = get_auth_settings()
    now = utc_now()
    users = UserRepository(session)
    user = await users.get_by_email(data.email, for_update=True)

    if user is None or not user.is_active:
        security.verify_password(data.password, None)
        raise InvalidCredentials()

    if user.locked_until is not None and user.locked_until > now:
        security.verify_password(data.password, None)
        raise InvalidCredentials()

    if not security.verify_password(data.password, user.hashed_password):
        attempts = user.failed_login_attempts + 1
        if attempts >= settings.login_max_failed_attempts:
            await users.update(
                user,
                {
                    "failed_login_attempts": 0,
                    "locked_until": now + timedelta(minutes=settings.login_lockout_minutes),
                },
            )
        else:
            await users.update(user, {"failed_login_attempts": attempts})
        raise InvalidCredentials()

    if user.failed_login_attempts or user.locked_until:
        await users.update(user, {"failed_login_attempts": 0, "locked_until": None})

    refresh_session = await SessionRepository(session).create_session(
        user_id=user.id,
        platform=data.platform,
        device_name=data.device_name,
        user_agent=client.user_agent,
        ip_address=client.ip_address,
        now=now,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    pair, _ = await _issue_token_pair(session, user, refresh_session, now)
    return pair


async def refresh(session: AsyncSession, raw_refresh_token: str) -> TokenPair:
    settings = get_auth_settings()
    now = utc_now()
    sessions = SessionRepository(session)
    token_hash = security.hash_refresh_token(raw_refresh_token)

    presented = await sessions.get_token_by_hash(token_hash)
    if presented is None:
        raise InvalidToken()

    refresh_session = await sessions.get_for_update(presented.session_id)
    if refresh_session is None or not refresh_session.is_active(now):
        raise SessionRevoked()

    presented = await sessions.get_token_by_hash(token_hash)
    if presented is None:
        raise InvalidToken()

    user = await UserRepository(session).get_by_id(refresh_session.user_id)
    if user is None or not user.is_active:
        raise SessionRevoked()

    if presented.rotated_at is None:
        return await _rotate(session, user, refresh_session, presented, now)

    active = await sessions.get_active_token(refresh_session.id)
    grace = timedelta(seconds=settings.refresh_reuse_grace_seconds)
    within_grace = (
        active is not None
        and presented.replaced_by_id == active.id
        and now - presented.rotated_at <= grace
    )
    if within_grace and active is not None:
        return await _rotate(session, user, refresh_session, active, now)

    await sessions.revoke(refresh_session, RevokedReason.REUSE_DETECTED, now)
    logger.warning("Reuso de refresh token detectado; sesión %s revocada", refresh_session.id)
    raise SessionRevoked()


async def logout(session: AsyncSession, session_id: uuid.UUID) -> None:
    sessions = SessionRepository(session)
    refresh_session = await sessions.get(session_id)
    if refresh_session is not None:
        await sessions.revoke(refresh_session, RevokedReason.LOGOUT, utc_now())


async def get_authenticated_user(session: AsyncSession, access_token: str) -> User:
    try:
        claims = security.decode_access_token(access_token)
    except security.InvalidAccessToken as exc:
        raise InvalidToken() from exc

    refresh_session = await SessionRepository(session).get(claims.session_id)
    if (
        refresh_session is None
        or refresh_session.user_id != claims.user_id
        or not refresh_session.is_active(utc_now())
    ):
        raise SessionRevoked()

    user = await UserRepository(session).get_by_id(claims.user_id)
    if user is None or not user.is_active:
        raise SessionRevoked()
    return user


async def verify_email(session: AsyncSession, data: VerifyEmailRequest) -> None:
    user = await UserRepository(session).get_by_email(data.email)
    if user is None or user.is_email_verified:
        raise OtpInvalid()
    now = await _consume_otp(session, user, OtpPurpose.EMAIL_VERIFICATION, data.code)
    await UserRepository(session).update(user, {"email_verified_at": now})


async def resend_email_verification(session: AsyncSession, email: str) -> OutgoingEmail | None:
    user = await UserRepository(session).get_by_email(email, for_update=True)
    if user is None or user.is_email_verified or not user.is_active:
        return None
    return await _issue_otp(session, user, OtpPurpose.EMAIL_VERIFICATION, enforce_limits=True)


async def request_password_reset(session: AsyncSession, email: str) -> OutgoingEmail | None:
    user = await UserRepository(session).get_by_email(email, for_update=True)
    if user is None or not _can_reset_password_by_email(user):
        return None
    return await _issue_otp(session, user, OtpPurpose.PASSWORD_RESET, enforce_limits=True)


async def confirm_password_reset(session: AsyncSession, data: PasswordResetConfirm) -> None:
    users = UserRepository(session)
    user = await users.get_by_email(data.email)
    if user is None or not _can_reset_password_by_email(user):
        raise OtpInvalid()
    now = await _consume_otp(session, user, OtpPurpose.PASSWORD_RESET, data.code)
    await users.update(
        user,
        {
            "hashed_password": security.hash_password(data.new_password),
            "failed_login_attempts": 0,
            "locked_until": None,
        },
    )
    await SessionRepository(session).revoke_all_for_user(user.id, RevokedReason.PASSWORD_RESET, now)


async def list_sessions(
    session: AsyncSession, *, user_id: uuid.UUID | None, active_only: bool
) -> list[SessionOut]:
    now = utc_now()
    rows = await SessionRepository(session).list_with_users(
        user_id=user_id, active_only=active_only, now=now
    )
    return [_session_out(refresh_session, user, now) for refresh_session, user in rows]


async def revoke_session_as_owner(
    session: AsyncSession, owner: User, session_id: uuid.UUID, client: ClientInfo
) -> None:
    sessions = SessionRepository(session)
    refresh_session = await sessions.get_for_update(session_id)
    if refresh_session is None:
        raise SessionNotFound()
    await sessions.revoke(refresh_session, RevokedReason.OWNER_REVOKED, utc_now())
    await audit_service.record(
        session,
        actor_user_id=owner.id,
        action=AuditAction.SESSION_REVOKED,
        target_type="refresh_session",
        target_id=session_id,
        ip_address=client.ip_address,
        details={"user_id": str(refresh_session.user_id)},
    )


async def revoke_user_sessions_as_owner(
    session: AsyncSession, owner: User, user_id: uuid.UUID, client: ClientInfo
) -> None:
    if await UserRepository(session).get_by_id(user_id) is None:
        raise UserNotFound()
    revoked = await SessionRepository(session).revoke_all_for_user(
        user_id, RevokedReason.OWNER_REVOKED_ALL, utc_now()
    )
    await audit_service.record(
        session,
        actor_user_id=owner.id,
        action=AuditAction.USER_SESSIONS_REVOKED,
        target_type="user",
        target_id=user_id,
        ip_address=client.ip_address,
        details={"revoked_sessions": revoked},
    )


async def create_owner(session: AsyncSession, data: OwnerCreate) -> User:
    users = UserRepository(session)
    if await users.get_owner() is not None:
        raise OwnerAlreadyExists()
    if await users.get_by_email(data.email) is not None:
        raise EmailAlreadyRegistered()
    owner = await users.create(
        email=data.email,
        hashed_password=security.hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        role=UserRole.OWNER,
    )
    await users.update(owner, {"email_verified_at": utc_now()})
    return owner


async def reset_owner_password(session: AsyncSession, new_password: str) -> User:
    users = UserRepository(session)
    owner = await users.get_owner()
    if owner is None:
        raise OwnerNotFound()
    now = utc_now()
    await users.update(
        owner,
        {
            "hashed_password": security.hash_password(new_password),
            "failed_login_attempts": 0,
            "locked_until": None,
        },
    )
    await SessionRepository(session).revoke_all_for_user(
        owner.id, RevokedReason.PASSWORD_RESET, now
    )
    return owner


async def _issue_token_pair(
    session: AsyncSession, user: User, refresh_session: RefreshSession, now: datetime
) -> tuple[TokenPair, RefreshToken]:
    raw_refresh = security.generate_refresh_token()
    token = await SessionRepository(session).add_token(
        refresh_session.id, security.hash_refresh_token(raw_refresh), now
    )
    access_token, expires_in = security.create_access_token(
        user.id, refresh_session.id, user.role.value, now
    )
    pair = TokenPair(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=expires_in,
        session_id=refresh_session.id,
    )
    return pair, token


async def _rotate(
    session: AsyncSession,
    user: User,
    refresh_session: RefreshSession,
    current: RefreshToken,
    now: datetime,
) -> TokenPair:
    settings = get_auth_settings()
    sessions = SessionRepository(session)
    await sessions.mark_rotated(current, now)
    pair, replacement = await _issue_token_pair(session, user, refresh_session, now)
    await sessions.set_replaced_by(current, replacement.id)
    await sessions.touch(
        refresh_session, now, now + timedelta(days=settings.refresh_token_expire_days)
    )
    return pair


async def _issue_otp(
    session: AsyncSession,
    user: User,
    purpose: OtpPurpose,
    *,
    enforce_limits: bool,
) -> OutgoingEmail | None:
    settings = get_auth_settings()
    now = utc_now()
    codes = OtpRepository(session, _OTP_MODELS[purpose])

    if enforce_limits:
        last_sent = await codes.latest_created_at(user.id)
        cooldown = timedelta(seconds=settings.otp_resend_cooldown_seconds)
        if last_sent is not None and now - last_sent < cooldown:
            return None
        sent_last_hour = await codes.count_created_since(user.id, now - timedelta(hours=1))
        if sent_last_hour >= settings.otp_max_resends_per_hour:
            return None

    await codes.invalidate_open(user.id, now)
    code = security.generate_otp()
    await codes.create(
        user.id,
        security.otp_hmac(purpose, user.id, code),
        now,
        now + timedelta(minutes=settings.otp_expire_minutes),
    )
    template = (
        templates.email_verification
        if purpose == OtpPurpose.EMAIL_VERIFICATION
        else templates.password_reset
    )
    return template(user.email, code, settings.otp_expire_minutes)


async def _consume_otp(
    session: AsyncSession, user: User, purpose: OtpPurpose, code: str
) -> datetime:
    settings = get_auth_settings()
    now = utc_now()
    codes = OtpRepository(session, _OTP_MODELS[purpose])
    record = await codes.get_open_for_update(user.id)
    if record is None or record.expires_at <= now:
        raise OtpInvalid()

    if not security.otp_matches(record.code_hmac, purpose, user.id, code):
        record.attempts += 1
        if record.attempts >= settings.otp_max_attempts:
            record.invalidated_at = now
        await codes.flush()
        raise OtpInvalid()

    record.consumed_at = now
    await codes.flush()
    return now


def _can_reset_password_by_email(user: User) -> bool:
    return user.is_active and user.role != UserRole.OWNER


def _session_out(refresh_session: RefreshSession, user: User, now: datetime) -> SessionOut:
    return SessionOut(
        id=refresh_session.id,
        user=SessionUserOut.model_validate(user),
        device_name=refresh_session.device_name,
        platform=refresh_session.platform,
        user_agent=refresh_session.user_agent,
        ip_address=refresh_session.ip_address,
        created_at=refresh_session.created_at,
        last_used_at=refresh_session.last_used_at,
        expires_at=refresh_session.expires_at,
        revoked_at=refresh_session.revoked_at,
        revoked_reason=refresh_session.revoked_reason,
        is_active=refresh_session.is_active(now),
    )
