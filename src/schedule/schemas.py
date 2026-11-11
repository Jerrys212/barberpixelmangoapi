import datetime as dt
import uuid
from collections import defaultdict
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from src.schedule.models import ExceptionKind

MAX_CLOSED_RANGE_DAYS = 366


def _validate_wall_time(value: dt.time) -> dt.time:
    if value.tzinfo is not None:
        raise ValueError("La hora es local del negocio: no lleva zona ni offset")
    if value.second or value.microsecond:
        raise ValueError("La hora debe tener formato HH:MM")
    return value


WallTime = Annotated[dt.time, AfterValidator(_validate_wall_time)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class _TimeRangeIn(BaseModel):
    start_time: WallTime
    end_time: WallTime

    @model_validator(mode="after")
    def _start_before_end(self) -> Self:
        if self.start_time >= self.end_time:
            raise ValueError("start_time debe ser anterior a end_time")
        return self


class WeeklyIntervalIn(_TimeRangeIn):
    weekday: int = Field(ge=0, le=6, description="0 = lunes … 6 = domingo")


class WeeklyScheduleIn(BaseModel):
    intervals: list[WeeklyIntervalIn] = Field(max_length=70)

    @model_validator(mode="after")
    def _no_overlaps(self) -> Self:
        by_day: defaultdict[int, list[WeeklyIntervalIn]] = defaultdict(list)
        for interval in self.intervals:
            by_day[interval.weekday].append(interval)
        for intervals in by_day.values():
            ordered = sorted(intervals, key=lambda i: i.start_time)
            for previous, current in pairwise(ordered):
                if current.start_time < previous.end_time:
                    raise ValueError("Los intervalos de un mismo día no pueden encimarse")
        return self


class WeeklyIntervalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: int
    start_time: dt.time
    end_time: dt.time


class ClosedDaysCreate(BaseModel):
    kind: Literal[ExceptionKind.CLOSED]
    date_from: dt.date
    date_to: dt.date | None = None
    reason: Reason | None = None

    @model_validator(mode="after")
    def _valid_range(self) -> Self:
        if self.last_date < self.date_from:
            raise ValueError("date_to no puede ser anterior a date_from")
        if (self.last_date - self.date_from).days >= MAX_CLOSED_RANGE_DAYS:
            raise ValueError(f"El rango no puede exceder {MAX_CLOSED_RANGE_DAYS} días")
        return self

    @property
    def last_date(self) -> dt.date:
        return self.date_to or self.date_from

    def dates(self) -> list[dt.date]:
        days = (self.last_date - self.date_from).days
        return [self.date_from + dt.timedelta(days=offset) for offset in range(days + 1)]


class TimedExceptionCreate(_TimeRangeIn):
    kind: Literal[ExceptionKind.SPECIAL_HOURS, ExceptionKind.BLOCK]
    date: dt.date
    reason: Reason | None = None


ExceptionCreate = Annotated[ClosedDaysCreate | TimedExceptionCreate, Field(discriminator="kind")]


class ExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ExceptionKind
    date: dt.date
    start_time: dt.time | None
    end_time: dt.time | None
    reason: str | None
    created_at: dt.datetime
