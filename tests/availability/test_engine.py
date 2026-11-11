import datetime as dt
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from src.availability.engine import (
    DayRules,
    InstantRange,
    SlotRequest,
    WallRange,
    compute_slots,
    occupied_range,
    resolve_day,
)

CDMX = ZoneInfo("America/Mexico_City")
DAY = dt.date(2026, 12, 1)
LONG_BEFORE = dt.datetime(2026, 11, 20, tzinfo=dt.UTC)
ONE_HOUR = dt.timedelta(hours=1)


def wall(start: str, end: str) -> WallRange:
    return WallRange(dt.time.fromisoformat(start), dt.time.fromisoformat(end))


def minutes(value: int) -> dt.timedelta:
    return dt.timedelta(minutes=value)


def slots(
    open_intervals: Sequence[WallRange],
    *,
    blocks: Sequence[WallRange] = (),
    busy: Sequence[InstantRange] = (),
    duration: int = 30,
    buffer: int = 10,
    step: int = 10,
    day: dt.date = DAY,
    tz: ZoneInfo = CDMX,
    now: dt.datetime = LONG_BEFORE,
    min_notice: dt.timedelta = ONE_HOUR,
    horizon: dt.timedelta = dt.timedelta(days=30),
) -> list[dt.datetime]:
    return compute_slots(
        SlotRequest(
            day=day,
            tz=tz,
            rules=DayRules(open_intervals=open_intervals, blocks=blocks),
            busy=busy,
            duration=minutes(duration),
            buffer=minutes(buffer),
            step=minutes(step),
            now=now,
            min_notice=min_notice,
            horizon=horizon,
        )
    )


def local_times(result: list[dt.datetime], tz: ZoneInfo = CDMX) -> list[str]:
    return [s.astimezone(tz).strftime("%H:%M") for s in result]


def local(hour: int, minute: int = 0, day: dt.date = DAY) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=CDMX)


class TestBuffer:
    def test_next_start_after_appointment_waits_for_buffer(self) -> None:
        appointment = occupied_range(local(16), local(16, 30), minutes(10))

        result = local_times(slots([wall("16:00", "18:00")], busy=[appointment]))

        assert "16:30" not in result
        assert result[0] == "16:40"

    def test_buffer_crossing_a_block_rejects_the_start(self) -> None:
        result = local_times(
            slots([wall("09:00", "12:00")], blocks=[wall("10:00", "11:00")], step=30)
        )

        assert "09:30" not in result
        assert result == ["09:00", "11:00", "11:30"]

    def test_buffer_may_run_past_closing_time(self) -> None:
        result = local_times(slots([wall("09:00", "10:00")], step=30))

        assert result == ["09:00", "09:30"]

    def test_new_slot_buffer_cannot_touch_next_appointment(self) -> None:
        appointment = occupied_range(local(10), local(10, 30), minutes(10))

        result = local_times(slots([wall("09:00", "11:00")], busy=[appointment]))

        assert "09:20" in result
        assert "09:30" not in result


class TestOpenIntervals:
    def test_several_intervals_in_one_day(self) -> None:
        result = local_times(
            slots([wall("09:00", "10:00"), wall("14:00", "15:00")], buffer=0, step=30)
        )

        assert result == ["09:00", "09:30", "14:00", "14:30"]

    def test_service_that_does_not_fit_at_the_end_is_excluded(self) -> None:
        result = local_times(slots([wall("09:00", "10:00")], duration=45, buffer=0))

        assert result == ["09:00", "09:10"]

    def test_partial_block_removes_only_its_range(self) -> None:
        result = local_times(
            slots([wall("09:00", "12:00")], blocks=[wall("10:00", "11:00")], buffer=0, step=30)
        )

        assert result == ["09:00", "09:30", "11:00", "11:30"]

    def test_adjacent_intervals_behave_as_one(self) -> None:
        result = local_times(
            slots([wall("09:00", "09:30"), wall("09:30", "10:00")], duration=40, buffer=0, step=20)
        )

        assert result == ["09:00", "09:20"]


class TestResolveDay:
    def test_closed_day_has_no_slots(self) -> None:
        rules = resolve_day(
            weekly=[wall("09:00", "18:00")], closed=True, special_hours=[], blocks=[]
        )

        assert rules.open_intervals == ()
        assert slots(rules.open_intervals) == []

    def test_special_hours_replace_weekly_schedule(self) -> None:
        rules = resolve_day(
            weekly=[wall("09:00", "18:00")],
            closed=False,
            special_hours=[wall("15:00", "16:00")],
            blocks=[],
        )

        assert local_times(slots(rules.open_intervals, buffer=0, step=30)) == ["15:00", "15:30"]

    def test_weekly_schedule_applies_without_special_hours(self) -> None:
        rules = resolve_day(
            weekly=[wall("09:00", "10:00")], closed=False, special_hours=[], blocks=[]
        )

        assert rules.open_intervals == [wall("09:00", "10:00")]


class TestTimezone:
    def test_local_start_is_converted_to_utc(self) -> None:
        result = slots([wall("16:40", "17:10")], buffer=0)

        assert result == [dt.datetime(2026, 12, 1, 22, 40, tzinfo=dt.UTC)]
        assert all(s.tzinfo == dt.UTC for s in result)

    def test_nonexistent_wall_times_are_skipped_on_dst_gap(self) -> None:
        new_york = ZoneInfo("America/New_York")
        spring_forward = dt.date(2027, 3, 14)

        result = slots(
            [wall("01:00", "04:00")],
            day=spring_forward,
            tz=new_york,
            buffer=0,
            step=30,
            now=dt.datetime(2027, 3, 1, tzinfo=dt.UTC),
        )

        assert local_times(result, new_york) == ["01:00", "01:30", "03:00", "03:30"]
        assert result[0] == dt.datetime(2027, 3, 14, 6, 0, tzinfo=dt.UTC)
        assert result[2] == dt.datetime(2027, 3, 14, 7, 0, tzinfo=dt.UTC)


class TestBookingWindow:
    def test_minimum_notice_hides_starts_too_soon(self) -> None:
        now = local(9, 5).astimezone(dt.UTC)

        result = local_times(slots([wall("09:00", "12:00")], step=30, now=now))

        assert result[0] == "10:30"

    def test_horizon_is_measured_by_instant(self) -> None:
        now = local(10, day=DAY - dt.timedelta(days=1)).astimezone(dt.UTC)

        result = local_times(
            slots(
                [wall("09:00", "12:00")],
                buffer=0,
                step=30,
                now=now,
                horizon=dt.timedelta(days=1),
            )
        )

        assert result == ["09:00", "09:30", "10:00"]
