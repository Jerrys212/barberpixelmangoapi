import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.catalog.test_router import create_service
from tests.conftest import owner_headers

URL = "/api/v1/availability"
CDMX = ZoneInfo("America/Mexico_City")
TARGET = dt.datetime.now(CDMX).date() + dt.timedelta(days=7)


async def setup_day(client: AsyncClient, session: AsyncSession) -> tuple[dict[str, str], str]:
    headers = await owner_headers(client, session)
    await client.put(
        "/api/v1/schedule/weekly",
        json={
            "intervals": [{"weekday": TARGET.weekday(), "start_time": "16:00", "end_time": "17:00"}]
        },
        headers=headers,
    )
    service = await create_service(client, headers, duration_minutes=30)
    return headers, service["id"]


async def availability(client: AsyncClient, service_id: str) -> dict[str, Any]:
    response = await client.get(URL, params={"service_id": service_id, "date": TARGET.isoformat()})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


class TestReadAvailability:
    async def test_returns_local_and_utc_starts_with_applied_rules(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, service_id = await setup_day(client, session)

        body = await availability(client, service_id)

        assert body["timezone"] == "America/Mexico_City"
        assert body["duration_minutes"] == 30
        assert body["buffer_minutes"] == 10
        assert [s["local_time"] for s in body["slots"]] == [
            "16:00:00",
            "16:10:00",
            "16:20:00",
            "16:30:00",
        ]
        expected_utc = dt.datetime.combine(TARGET, dt.time(16), tzinfo=CDMX).astimezone(dt.UTC)
        assert dt.datetime.fromisoformat(body["slots"][0]["start_at"]) == expected_utc

    async def test_block_removes_its_range(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers, service_id = await setup_day(client, session)
        await client.post(
            "/api/v1/schedule/exceptions",
            json={
                "kind": "BLOCK",
                "date": TARGET.isoformat(),
                "start_time": "16:40",
                "end_time": "17:00",
            },
            headers=headers,
        )

        body = await availability(client, service_id)

        assert [s["local_time"] for s in body["slots"]] == ["16:00:00"]

    async def test_closed_day_has_no_slots(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers, service_id = await setup_day(client, session)
        await client.post(
            "/api/v1/schedule/exceptions",
            json={"kind": "CLOSED", "date_from": TARGET.isoformat()},
            headers=headers,
        )

        assert (await availability(client, service_id))["slots"] == []

    async def test_inactive_service_is_404(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers, service_id = await setup_day(client, session)
        await client.patch(
            f"/api/v1/services/{service_id}", json={"is_active": False}, headers=headers
        )

        response = await client.get(
            URL, params={"service_id": service_id, "date": TARGET.isoformat()}
        )

        assert response.status_code == 404
        assert response.json()["code"] == "SERVICE_NOT_FOUND"

    async def test_date_beyond_horizon_has_no_slots(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        _, service_id = await setup_day(client, session)
        far = TARGET + dt.timedelta(days=35)

        response = await client.get(URL, params={"service_id": service_id, "date": far.isoformat()})

        assert response.json()["slots"] == []
