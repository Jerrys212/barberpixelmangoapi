import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CHAR, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class SessionPlatform(StrEnum):
    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB = "WEB"
    OTHER = "OTHER"


class RevokedReason(StrEnum):
    LOGOUT = "LOGOUT"
    OWNER_REVOKED = "OWNER_REVOKED"
    OWNER_REVOKED_ALL = "OWNER_REVOKED_ALL"
    REUSE_DETECTED = "REUSE_DETECTED"
    PASSWORD_RESET = "PASSWORD_RESET"  # noqa: S105


def _string_enum(enum_cls: type[StrEnum], name: str, length: int) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda enum: [member.value for member in enum],
    )


class RefreshSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "refresh_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    device_name: Mapped[str | None] = mapped_column(String(100))
    platform: Mapped[SessionPlatform] = mapped_column(
        _string_enum(SessionPlatform, "session_platform", 16)
    )
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[RevokedReason | None] = mapped_column(
        _string_enum(RevokedReason, "revoked_reason", 32)
    )

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


class RefreshToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index(
            "uq_refresh_tokens_one_active_per_session",
            "session_id",
            unique=True,
            postgresql_where=text("rotated_at IS NULL"),
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )


class OtpCodeMixin(UUIDPrimaryKeyMixin, CreatedAtMixin):
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    code_hmac: Mapped[str] = mapped_column(CHAR(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailVerificationCode(OtpCodeMixin, Base):
    __tablename__ = "email_verification_codes"
    __table_args__ = (Index("ix_email_verification_codes_user_created", "user_id", "created_at"),)


class PasswordResetCode(OtpCodeMixin, Base):
    __tablename__ = "password_reset_codes"
    __table_args__ = (Index("ix_password_reset_codes_user_created", "user_id", "created_at"),)


OtpCode = EmailVerificationCode | PasswordResetCode
