"""Pure availability calculation: no database, no clock. Everything comes in as arguments."""

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class WallRange:
    start: dt.time
    end: dt.time


@dataclass(frozen=True, slots=True)
class InstantRange:
    start: dt.datetime
    end: dt.datetime

    def overlaps(self, other: InstantRange) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: InstantRange) -> bool:
        return self.start <= other.start and other.end <= self.end


@dataclass(frozen=True, slots=True)
class DayRules:
    open_intervals: Sequence[WallRange]
    blocks: Sequence[WallRange]


@dataclass(frozen=True, slots=True)
class SlotRequest:
    day: dt.date
    tz: ZoneInfo
    rules: DayRules
    busy: Sequence[InstantRange]
    duration: dt.timedelta
    buffer: dt.timedelta
    step: dt.timedelta
    now: dt.datetime
    min_notice: dt.timedelta
    horizon: dt.timedelta


def occupied_range(start: dt.datetime, end: dt.datetime, buffer: dt.timedelta) -> InstantRange:
    """Single occupancy rule shared with appointments: an appointment blocks until end + buffer."""
    return InstantRange(start, end + buffer)


def resolve_day(
    *,
    weekly: Iterable[WallRange],
    closed: bool,
    special_hours: Iterable[WallRange],
    blocks: Iterable[WallRange],
) -> DayRules:
    if closed:
        return DayRules(open_intervals=(), blocks=())
    special = list(special_hours)
    return DayRules(open_intervals=special or list(weekly), blocks=list(blocks))


def local_instant(day: dt.date, wall: dt.time, tz: ZoneInfo) -> dt.datetime | None:
    """Local wall time to UTC; None when the wall time does not exist (DST gap)."""
    local = dt.datetime.combine(day, wall, tzinfo=tz)
    instant = local.astimezone(dt.UTC)
    if instant.astimezone(tz).replace(tzinfo=None) != local.replace(tzinfo=None):
        return None
    return instant


def _wall_to_instants(day: dt.date, wall: WallRange, tz: ZoneInfo) -> InstantRange:
    start = dt.datetime.combine(day, wall.start, tzinfo=tz).astimezone(dt.UTC)
    end = dt.datetime.combine(day, wall.end, tzinfo=tz).astimezone(dt.UTC)
    return InstantRange(start, end)


def _merge(intervals: Sequence[WallRange]) -> list[WallRange]:
    merged: list[WallRange] = []
    for interval in sorted(intervals, key=lambda i: i.start):
        if merged and interval.start <= merged[-1].end:
            last = merged.pop()
            interval = WallRange(last.start, max(last.end, interval.end))
        merged.append(interval)
    return merged


def compute_slots(request: SlotRequest) -> list[dt.datetime]:
    tz, day = request.tz, request.day
    blocks = [_wall_to_instants(day, block, tz) for block in request.rules.blocks]
    earliest = request.now + request.min_notice
    latest = request.now + request.horizon

    slots: list[dt.datetime] = []
    for wall in _merge(request.rules.open_intervals):
        opening = _wall_to_instants(day, wall, tz)
        cursor = dt.datetime.combine(day, wall.start)
        closing = dt.datetime.combine(day, wall.end)
        while cursor < closing:
            start = local_instant(day, cursor.time(), tz)
            cursor += request.step
            if start is None or not earliest <= start <= latest:
                continue
            service = InstantRange(start, start + request.duration)
            occupied = occupied_range(service.start, service.end, request.buffer)
            if not opening.contains(service):
                continue
            if any(occupied.overlaps(block) for block in blocks):
                continue
            if any(occupied.overlaps(busy) for busy in request.busy):
                continue
            slots.append(start)
    return sorted(set(slots))
