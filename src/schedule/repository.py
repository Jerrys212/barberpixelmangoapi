import datetime as dt
import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.schedule.models import ScheduleException, WeeklyInterval


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_weekly(self, weekday: int | None = None) -> Sequence[WeeklyInterval]:
        query = select(WeeklyInterval).order_by(WeeklyInterval.weekday, WeeklyInterval.start_time)
        if weekday is not None:
            query = query.where(WeeklyInterval.weekday == weekday)
        return (await self.session.execute(query)).scalars().all()

    async def replace_weekly(self, intervals: Iterable[WeeklyInterval]) -> None:
        await self.session.execute(delete(WeeklyInterval))
        self.session.add_all(intervals)
        await self.session.flush()

    async def list_exceptions(
        self, date_from: dt.date, date_to: dt.date
    ) -> Sequence[ScheduleException]:
        result = await self.session.execute(
            select(ScheduleException)
            .where(ScheduleException.date.between(date_from, date_to))
            .order_by(
                ScheduleException.date,
                ScheduleException.start_time.nulls_first(),
                ScheduleException.id,
            )
        )
        return result.scalars().all()

    async def get_exception(self, exception_id: uuid.UUID) -> ScheduleException | None:
        return await self.session.get(ScheduleException, exception_id)

    async def add_exceptions(self, exceptions: list[ScheduleException]) -> list[ScheduleException]:
        self.session.add_all(exceptions)
        await self.session.flush()
        return exceptions

    async def delete_exception(self, exception: ScheduleException) -> None:
        await self.session.delete(exception)
        await self.session.flush()
