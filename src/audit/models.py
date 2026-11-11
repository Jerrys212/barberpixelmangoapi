import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class AuditAction(StrEnum):
    SESSION_REVOKED = "SESSION_REVOKED"
    USER_SESSIONS_REVOKED = "USER_SESSIONS_REVOKED"
    BUSINESS_UPDATED = "BUSINESS_UPDATED"
    SCHEDULE_UPDATED = "SCHEDULE_UPDATED"
    EXCEPTION_CREATED = "EXCEPTION_CREATED"
    EXCEPTION_DELETED = "EXCEPTION_DELETED"


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(
            AuditAction,
            name="audit_action",
            native_enum=False,
            create_constraint=True,
            length=64,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[uuid.UUID | None]
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45))
