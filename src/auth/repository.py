import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import (
    EmailVerificationCode,
    OtpCode,
    PasswordResetCode,
    RefreshSession,
    RefreshToken,
    RevokedReason,
    SessionPlatform,
)
from src.users.models import User

OtpModel = type[EmailVerificationCode] | type[PasswordResetCode]


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        platform: SessionPlatform,
        device_name: str | None,
        user_agent: str | None,
        ip_address: str | None,
        now: datetime,
        expires_at: datetime,
    ) -> RefreshSession:
        refresh_session = RefreshSession(
            user_id=user_id,
            platform=platform,
            device_name=device_name,
            user_agent=user_agent,
            ip_address=ip_address,
            created_at=now,
            last_used_at=now,
            expires_at=expires_at,
        )
        self.session.add(refresh_session)
        await self.session.flush()
        return refresh_session

    async def get(self, session_id: uuid.UUID) -> RefreshSession | None:
        return await self.session.get(RefreshSession, session_id)

    async def get_for_update(self, session_id: uuid.UUID) -> RefreshSession | None:
        result = await self.session.execute(
            select(RefreshSession)
            .where(RefreshSession.id == session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def add_token(
        self, session_id: uuid.UUID, token_hash: str, now: datetime
    ) -> RefreshToken:
        token = RefreshToken(session_id=session_id, token_hash=token_hash, created_at=now)
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_token_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_active_token(self, session_id: uuid.UUID) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken)
            .where(RefreshToken.session_id == session_id, RefreshToken.rotated_at.is_(None))
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def mark_rotated(self, token: RefreshToken, now: datetime) -> None:
        token.rotated_at = now
        await self.session.flush()

    async def set_replaced_by(self, token: RefreshToken, replacement_id: uuid.UUID) -> None:
        token.replaced_by_id = replacement_id
        await self.session.flush()

    async def touch(
        self, refresh_session: RefreshSession, now: datetime, expires_at: datetime
    ) -> None:
        refresh_session.last_used_at = now
        refresh_session.expires_at = expires_at
        await self.session.flush()

    async def revoke(
        self, refresh_session: RefreshSession, reason: RevokedReason, now: datetime
    ) -> None:
        if refresh_session.revoked_at is None:
            refresh_session.revoked_at = now
            refresh_session.revoked_reason = reason
            await self.session.flush()

    async def revoke_all_for_user(
        self, user_id: uuid.UUID, reason: RevokedReason, now: datetime
    ) -> int:
        result = await self.session.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
            .execution_options(synchronize_session="fetch")
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def list_with_users(
        self, *, user_id: uuid.UUID | None, active_only: bool, now: datetime
    ) -> list[tuple[RefreshSession, User]]:
        query = (
            select(RefreshSession, User)
            .join(User, User.id == RefreshSession.user_id)
            .order_by(RefreshSession.last_used_at.desc())
        )
        if user_id is not None:
            query = query.where(RefreshSession.user_id == user_id)
        if active_only:
            query = query.where(
                RefreshSession.revoked_at.is_(None), RefreshSession.expires_at > now
            )
        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]


class OtpRepository:
    def __init__(self, session: AsyncSession, model: OtpModel) -> None:
        self.session = session
        self.model = model

    async def latest_created_at(self, user_id: uuid.UUID) -> datetime | None:
        result = await self.session.execute(
            select(func.max(self.model.created_at)).where(self.model.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def count_created_since(self, user_id: uuid.UUID, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(self.model)
            .where(self.model.user_id == user_id, self.model.created_at >= since)
        )
        return int(result.scalar_one())

    async def invalidate_open(self, user_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.consumed_at.is_(None),
                self.model.invalidated_at.is_(None),
            )
            .values(invalidated_at=now)
            .execution_options(synchronize_session="fetch")
        )

    async def create(
        self, user_id: uuid.UUID, code_hmac: str, now: datetime, expires_at: datetime
    ) -> OtpCode:
        code = self.model(
            user_id=user_id, code_hmac=code_hmac, created_at=now, expires_at=expires_at
        )
        self.session.add(code)
        await self.session.flush()
        return code

    async def get_open_for_update(self, user_id: uuid.UUID) -> OtpCode | None:
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.consumed_at.is_(None),
                self.model.invalidated_at.is_(None),
            )
            .order_by(self.model.created_at.desc())
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return cast(OtpCode | None, result.scalar_one_or_none())

    async def flush(self) -> None:
        await self.session.flush()
