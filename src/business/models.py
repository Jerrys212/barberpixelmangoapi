from zoneinfo import ZoneInfo

from sqlalchemy import CheckConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

DEFAULT_NAME = "BarberPixelMango"
DEFAULT_TIMEZONE = "America/Mexico_City"
DEFAULT_CURRENCY = "MXN"


def _int_column(default: int) -> Mapped[int]:
    return mapped_column(default=default, server_default=text(str(default)))


class BusinessProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_profile"
    __table_args__ = (
        CheckConstraint("singleton", name="singleton"),
        CheckConstraint("currency = 'MXN'", name="currency_mxn"),
        CheckConstraint("slot_interval_minutes BETWEEN 5 AND 60", name="slot_interval_range"),
        CheckConstraint("buffer_minutes BETWEEN 0 AND 120", name="buffer_range"),
        CheckConstraint("hold_minutes BETWEEN 5 AND 60", name="hold_range"),
        CheckConstraint(
            "cancellation_window_minutes BETWEEN 0 AND 10080", name="cancellation_window_range"
        ),
        CheckConstraint("min_notice_minutes BETWEEN 0 AND 10080", name="min_notice_range"),
        CheckConstraint("booking_horizon_days BETWEEN 1 AND 365", name="booking_horizon_range"),
    )

    singleton: Mapped[bool] = mapped_column(unique=True, default=True, server_default=text("true"))
    name: Mapped[str] = mapped_column(
        String(120), default=DEFAULT_NAME, server_default=DEFAULT_NAME
    )
    phone: Mapped[str | None] = mapped_column(String(16))
    address: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(
        String(64), default=DEFAULT_TIMEZONE, server_default=DEFAULT_TIMEZONE
    )
    currency: Mapped[str] = mapped_column(
        String(3), default=DEFAULT_CURRENCY, server_default=DEFAULT_CURRENCY
    )
    slot_interval_minutes: Mapped[int] = _int_column(10)
    buffer_minutes: Mapped[int] = _int_column(10)
    hold_minutes: Mapped[int] = _int_column(10)
    cancellation_window_minutes: Mapped[int] = _int_column(24 * 60)
    min_notice_minutes: Mapped[int] = _int_column(60)
    booking_horizon_days: Mapped[int] = _int_column(30)

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
