from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    OWNER = "OWNER"
    CUSTOMER = "CUSTOMER"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_single_owner",
            "role",
            unique=True,
            postgresql_where=text("role = 'OWNER'"),
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(16))
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None
