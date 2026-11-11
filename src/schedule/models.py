import datetime as dt
import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class WeeklyInterval(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "business_schedules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("start_time < end_time", name="start_before_end"),
    )

    weekday: Mapped[int] = mapped_column(SmallInteger, index=True)
    start_time: Mapped[dt.time]
    end_time: Mapped[dt.time]


class ExceptionKind(StrEnum):
    CLOSED = "CLOSED"
    SPECIAL_HOURS = "SPECIAL_HOURS"
    BLOCK = "BLOCK"


class ScheduleException(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "schedule_exceptions"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'CLOSED' AND start_time IS NULL AND end_time IS NULL)"
            " OR (kind <> 'CLOSED' AND start_time IS NOT NULL AND end_time IS NOT NULL"
            " AND start_time < end_time)",
            name="times_match_kind",
        ),
        Index(
            "uq_schedule_exceptions_closed_date",
            "date",
            unique=True,
            postgresql_where=text("kind = 'CLOSED'"),
        ),
    )

    kind: Mapped[ExceptionKind] = mapped_column(
        Enum(
            ExceptionKind,
            name="exception_kind",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    date: Mapped[dt.date] = mapped_column(index=True)
    start_time: Mapped[dt.time | None]
    end_time: Mapped[dt.time | None]
    reason: Mapped[str | None] = mapped_column(String(255))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
