import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.availability.engine import (
    InstantRange,
    SlotRequest,
    WallRange,
    compute_slots,
    resolve_day,
)
from src.availability.schemas import AvailabilityOut, SlotOut
from src.business import service as business_service
from src.catalog import service as catalog_service
from src.models import utc_now
from src.schedule import service as schedule_service
from src.schedule.models import ExceptionKind, ScheduleException


def _walls(exceptions: list[ScheduleException], kind: ExceptionKind) -> list[WallRange]:
    return [
        WallRange(e.start_time, e.end_time)
        for e in exceptions
        if e.kind == kind and e.start_time is not None and e.end_time is not None
    ]


async def get_availability(
    session: AsyncSession, service_id: uuid.UUID, day: dt.date
) -> AvailabilityOut:
    service = await catalog_service.get_bookable_service(session, service_id)
    profile = await business_service.get_profile(session)
    weekly, exceptions = await schedule_service.get_day(session, day)
    day_exceptions = list(exceptions)

    rules = resolve_day(
        weekly=[WallRange(i.start_time, i.end_time) for i in weekly],
        closed=any(e.kind == ExceptionKind.CLOSED for e in day_exceptions),
        special_hours=_walls(day_exceptions, ExceptionKind.SPECIAL_HOURS),
        blocks=_walls(day_exceptions, ExceptionKind.BLOCK),
    )
    # Appointments arrive in phase 3; until then nothing else occupies the calendar.
    busy: list[InstantRange] = []
    tz = profile.zone
    slots = compute_slots(
        SlotRequest(
            day=day,
            tz=tz,
            rules=rules,
            busy=busy,
            duration=dt.timedelta(minutes=service.duration_minutes),
            buffer=dt.timedelta(minutes=profile.buffer_minutes),
            step=dt.timedelta(minutes=profile.slot_interval_minutes),
            now=utc_now(),
            min_notice=dt.timedelta(minutes=profile.min_notice_minutes),
            horizon=dt.timedelta(days=profile.booking_horizon_days),
        )
    )
    return AvailabilityOut(
        service_id=service.id,
        date=day,
        timezone=profile.timezone,
        duration_minutes=service.duration_minutes,
        buffer_minutes=profile.buffer_minutes,
        slots=[SlotOut(start_at=s, local_time=s.astimezone(tz).time()) for s in slots],
    )
