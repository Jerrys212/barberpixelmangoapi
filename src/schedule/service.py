import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import service as audit_service
from src.audit.models import AuditAction
from src.auth.service import ClientInfo
from src.business import service as business_service
from src.models import utc_now
from src.schedule.exceptions import (
    ExceptionConflict,
    ExceptionDateInPast,
    ExceptionNotFound,
    InvalidDateRange,
)
from src.schedule.models import ExceptionKind, ScheduleException, WeeklyInterval
from src.schedule.repository import ScheduleRepository
from src.schedule.schemas import (
    MAX_CLOSED_RANGE_DAYS,
    ClosedDaysCreate,
    ExceptionCreate,
    WeeklyScheduleIn,
)
from src.users.models import User


def _interval_details(interval: WeeklyInterval) -> dict[str, Any]:
    return {
        "weekday": interval.weekday,
        "start_time": interval.start_time.isoformat("minutes"),
        "end_time": interval.end_time.isoformat("minutes"),
    }


def _exception_details(exception: ScheduleException) -> dict[str, Any]:
    return {
        "id": str(exception.id),
        "kind": exception.kind.value,
        "date": exception.date.isoformat(),
        "start_time": exception.start_time.isoformat("minutes") if exception.start_time else None,
        "end_time": exception.end_time.isoformat("minutes") if exception.end_time else None,
        "reason": exception.reason,
    }


def _overlaps(a: ScheduleException, b: ScheduleException) -> bool:
    a_start, a_end, b_start, b_end = a.start_time, a.end_time, b.start_time, b.end_time
    if a_start is None or a_end is None or b_start is None or b_end is None:
        return False
    return a_start < b_end and b_start < a_end


def _find_conflict(new: ScheduleException, existing: Sequence[ScheduleException]) -> bool:
    same_day = [other for other in existing if other.date == new.date]
    if new.kind == ExceptionKind.CLOSED:
        return any(other.kind != ExceptionKind.BLOCK for other in same_day)
    if new.kind == ExceptionKind.SPECIAL_HOURS:
        return any(
            other.kind == ExceptionKind.CLOSED
            or (other.kind == ExceptionKind.SPECIAL_HOURS and _overlaps(new, other))
            for other in same_day
        )
    return False


async def get_weekly(session: AsyncSession) -> Sequence[WeeklyInterval]:
    return await ScheduleRepository(session).list_weekly()


async def replace_weekly(
    session: AsyncSession, owner: User, data: WeeklyScheduleIn, client: ClientInfo
) -> Sequence[WeeklyInterval]:
    profile = await business_service.lock_calendar(session)
    repo = ScheduleRepository(session)
    previous = [_interval_details(interval) for interval in await repo.list_weekly()]
    await repo.replace_weekly(
        WeeklyInterval(weekday=i.weekday, start_time=i.start_time, end_time=i.end_time)
        for i in data.intervals
    )
    current = await repo.list_weekly()
    await audit_service.record(
        session,
        actor_user_id=owner.id,
        action=AuditAction.SCHEDULE_UPDATED,
        target_type="business_schedules",
        target_id=profile.id,
        ip_address=client.ip_address,
        details={"old": previous, "new": [_interval_details(i) for i in current]},
    )
    return current


async def list_exceptions(
    session: AsyncSession, date_from: dt.date, date_to: dt.date
) -> Sequence[ScheduleException]:
    if date_to < date_from or (date_to - date_from).days >= MAX_CLOSED_RANGE_DAYS:
        raise InvalidDateRange()
    return await ScheduleRepository(session).list_exceptions(date_from, date_to)


async def create_exceptions(
    session: AsyncSession, owner: User, data: ExceptionCreate, client: ClientInfo
) -> list[ScheduleException]:
    profile = await business_service.lock_calendar(session)
    if isinstance(data, ClosedDaysCreate):
        new = [
            ScheduleException(
                kind=ExceptionKind.CLOSED, date=day, reason=data.reason, created_by_id=owner.id
            )
            for day in data.dates()
        ]
    else:
        new = [
            ScheduleException(
                kind=data.kind,
                date=data.date,
                start_time=data.start_time,
                end_time=data.end_time,
                reason=data.reason,
                created_by_id=owner.id,
            )
        ]

    first_day, last_day = new[0].date, new[-1].date
    if first_day < utc_now().astimezone(profile.zone).date():
        raise ExceptionDateInPast()
    repo = ScheduleRepository(session)
    existing = await repo.list_exceptions(first_day, last_day)
    if any(_find_conflict(exception, existing) for exception in new):
        raise ExceptionConflict()

    created = await repo.add_exceptions(new)
    await audit_service.record(
        session,
        actor_user_id=owner.id,
        action=AuditAction.EXCEPTION_CREATED,
        target_type="schedule_exception",
        target_id=created[0].id if len(created) == 1 else None,
        ip_address=client.ip_address,
        details={"exceptions": [_exception_details(exception) for exception in created]},
    )
    return created


async def delete_exception(
    session: AsyncSession, owner: User, exception_id: uuid.UUID, client: ClientInfo
) -> None:
    await business_service.lock_calendar(session)
    repo = ScheduleRepository(session)
    exception = await repo.get_exception(exception_id)
    if exception is None:
        raise ExceptionNotFound()
    details = _exception_details(exception)
    await repo.delete_exception(exception)
    await audit_service.record(
        session,
        actor_user_id=owner.id,
        action=AuditAction.EXCEPTION_DELETED,
        target_type="schedule_exception",
        target_id=exception_id,
        ip_address=client.ip_address,
        details=details,
    )


async def get_day(
    session: AsyncSession, day: dt.date
) -> tuple[Sequence[WeeklyInterval], Sequence[ScheduleException]]:
    repo = ScheduleRepository(session)
    return await repo.list_weekly(day.weekday()), await repo.list_exceptions(day, day)
