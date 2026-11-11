import datetime as dt
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.models import AuditAction
from tests.conftest import audit_entries, customer_headers, owner_headers

WEEKLY_URL = "/api/v1/schedule/weekly"
EXCEPTIONS_URL = "/api/v1/schedule/exceptions"


def local_today() -> dt.date:
    return dt.datetime.now(ZoneInfo("America/Mexico_City")).date()


def in_days(days: int) -> str:
    return (local_today() + dt.timedelta(days=days)).isoformat()


class TestReplaceWeekly:
    async def test_owner_sets_several_intervals_per_day_and_it_is_audited(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        intervals = [
            {"weekday": 0, "start_time": "09:00", "end_time": "13:00"},
            {"weekday": 0, "start_time": "14:00", "end_time": "19:00"},
        ]

        response = await client.put(WEEKLY_URL, json={"intervals": intervals}, headers=headers)
        public = await client.get(WEEKLY_URL)

        assert response.status_code == 200
        assert public.json() == [
            {"weekday": 0, "start_time": "09:00:00", "end_time": "13:00:00"},
            {"weekday": 0, "start_time": "14:00:00", "end_time": "19:00:00"},
        ]
        [entry] = await audit_entries(session, AuditAction.SCHEDULE_UPDATED)
        assert entry.details["old"] == []
        assert len(entry.details["new"]) == 2

    async def test_replacing_drops_previous_intervals(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        first = [{"weekday": 1, "start_time": "09:00", "end_time": "13:00"}]
        second = [{"weekday": 2, "start_time": "10:00", "end_time": "12:00"}]
        await client.put(WEEKLY_URL, json={"intervals": first}, headers=headers)

        await client.put(WEEKLY_URL, json={"intervals": second}, headers=headers)

        assert [i["weekday"] for i in (await client.get(WEEKLY_URL)).json()] == [2]

    async def test_rejects_overlapping_intervals(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        intervals = [
            {"weekday": 0, "start_time": "09:00", "end_time": "13:00"},
            {"weekday": 0, "start_time": "12:00", "end_time": "15:00"},
        ]

        response = await client.put(WEEKLY_URL, json={"intervals": intervals}, headers=headers)

        assert response.status_code == 422

    async def test_rejects_end_before_start(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        intervals = [{"weekday": 0, "start_time": "13:00", "end_time": "09:00"}]

        response = await client.put(WEEKLY_URL, json={"intervals": intervals}, headers=headers)

        assert response.status_code == 422

    async def test_customer_gets_403(self, client: AsyncClient, session: AsyncSession) -> None:
        headers = await customer_headers(client, session)

        response = await client.put(WEEKLY_URL, json={"intervals": []}, headers=headers)

        assert response.status_code == 403


class TestCreateExceptions:
    async def test_closed_date_range_creates_one_row_per_day_in_one_audit_entry(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        response = await client.post(
            EXCEPTIONS_URL,
            json={"kind": "CLOSED", "date_from": in_days(3), "date_to": in_days(6)},
            headers=headers,
        )

        assert response.status_code == 201
        assert [e["date"] for e in response.json()] == [in_days(d) for d in range(3, 7)]
        [entry] = await audit_entries(session, AuditAction.EXCEPTION_CREATED)
        assert len(entry.details["exceptions"]) == 4

    async def test_closed_range_is_all_or_nothing(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        await client.post(
            EXCEPTIONS_URL,
            json={
                "kind": "SPECIAL_HOURS",
                "date": in_days(5),
                "start_time": "10:00",
                "end_time": "14:00",
            },
            headers=headers,
        )

        response = await client.post(
            EXCEPTIONS_URL,
            json={"kind": "CLOSED", "date_from": in_days(3), "date_to": in_days(6)},
            headers=headers,
        )
        listed = await client.get(
            EXCEPTIONS_URL,
            params={"date_from": in_days(0), "date_to": in_days(10)},
            headers=headers,
        )

        assert response.status_code == 409
        assert [e["kind"] for e in listed.json()] == ["SPECIAL_HOURS"]

    async def test_rejects_past_dates(self, client: AsyncClient, session: AsyncSession) -> None:
        headers = await owner_headers(client, session)

        closed = await client.post(
            EXCEPTIONS_URL,
            json={"kind": "CLOSED", "date_from": in_days(-1), "date_to": in_days(2)},
            headers=headers,
        )
        block = await client.post(
            EXCEPTIONS_URL,
            json={"kind": "BLOCK", "date": in_days(-1), "start_time": "10:00", "end_time": "11:00"},
            headers=headers,
        )

        assert closed.status_code == block.status_code == 400
        assert closed.json()["code"] == "EXCEPTION_DATE_IN_PAST"

    async def test_today_is_allowed(self, client: AsyncClient, session: AsyncSession) -> None:
        headers = await owner_headers(client, session)

        response = await client.post(
            EXCEPTIONS_URL,
            json={"kind": "BLOCK", "date": in_days(0), "start_time": "10:00", "end_time": "11:00"},
            headers=headers,
        )

        assert response.status_code == 201

    async def test_special_hours_on_closed_date_conflict(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        await client.post(
            EXCEPTIONS_URL, json={"kind": "CLOSED", "date_from": in_days(2)}, headers=headers
        )

        response = await client.post(
            EXCEPTIONS_URL,
            json={
                "kind": "SPECIAL_HOURS",
                "date": in_days(2),
                "start_time": "10:00",
                "end_time": "14:00",
            },
            headers=headers,
        )

        assert response.status_code == 409
        assert response.json()["code"] == "EXCEPTION_CONFLICT"

    async def test_overlapping_special_hours_conflict(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        special = {
            "kind": "SPECIAL_HOURS",
            "date": in_days(2),
            "start_time": "10:00",
            "end_time": "14:00",
        }
        await client.post(EXCEPTIONS_URL, json=special, headers=headers)

        overlapping = await client.post(
            EXCEPTIONS_URL,
            json={**special, "start_time": "13:00", "end_time": "15:00"},
            headers=headers,
        )
        separate = await client.post(
            EXCEPTIONS_URL,
            json={**special, "start_time": "16:00", "end_time": "18:00"},
            headers=headers,
        )

        assert overlapping.status_code == 409
        assert separate.status_code == 201

    async def test_rejects_range_with_end_before_start(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        response = await client.post(
            EXCEPTIONS_URL,
            json={"kind": "CLOSED", "date_from": in_days(5), "date_to": in_days(3)},
            headers=headers,
        )

        assert response.status_code == 422

    async def test_customer_gets_403(self, client: AsyncClient, session: AsyncSession) -> None:
        headers = await customer_headers(client, session)

        response = await client.post(
            EXCEPTIONS_URL, json={"kind": "CLOSED", "date_from": in_days(2)}, headers=headers
        )

        assert response.status_code == 403


class TestDeleteException:
    async def test_owner_deletes_and_it_is_audited(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        created = await client.post(
            EXCEPTIONS_URL, json={"kind": "CLOSED", "date_from": in_days(2)}, headers=headers
        )
        exception_id = created.json()[0]["id"]

        response = await client.delete(f"{EXCEPTIONS_URL}/{exception_id}", headers=headers)
        again = await client.delete(f"{EXCEPTIONS_URL}/{exception_id}", headers=headers)

        assert response.status_code == 204
        assert again.status_code == 404
        [entry] = await audit_entries(session, AuditAction.EXCEPTION_DELETED)
        assert entry.details["kind"] == "CLOSED"
