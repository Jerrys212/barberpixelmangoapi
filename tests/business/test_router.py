from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.models import AuditAction
from tests.conftest import audit_entries, customer_headers, owner_headers

URL = "/api/v1/business"


class TestReadBusiness:
    async def test_public_profile_has_initial_values(self, client: AsyncClient) -> None:
        response = await client.get(URL)

        assert response.status_code == 200
        body = response.json()
        assert body["timezone"] == "America/Mexico_City"
        assert body["currency"] == "MXN"
        assert body["slot_interval_minutes"] == 10
        assert body["buffer_minutes"] == 10
        assert body["hold_minutes"] == 10
        assert body["cancellation_window_minutes"] == 24 * 60
        assert body["min_notice_minutes"] == 60
        assert body["booking_horizon_days"] == 30
        assert body["phone"] is None
        assert body["address"] is None


class TestUpdateBusiness:
    async def test_owner_updates_and_change_is_audited_with_old_and_new_values(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        response = await client.patch(
            URL,
            json={"buffer_minutes": 15, "phone": "5511223344", "address": "Av. Siempre Viva 1"},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["buffer_minutes"] == 15
        [entry] = await audit_entries(session, AuditAction.BUSINESS_UPDATED)
        assert entry.details["changes"]["buffer_minutes"] == {"old": 10, "new": 15}
        assert entry.details["changes"]["phone"] == {"old": None, "new": "5511223344"}

    async def test_unchanged_values_are_not_audited(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        response = await client.patch(URL, json={"buffer_minutes": 10}, headers=headers)

        assert response.status_code == 200
        assert await audit_entries(session, AuditAction.BUSINESS_UPDATED) == []

    async def test_optional_contact_fields_can_be_cleared(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        await client.patch(URL, json={"address": "Calle 1"}, headers=headers)

        response = await client.patch(URL, json={"address": None}, headers=headers)

        assert response.json()["address"] is None

    async def test_required_fields_reject_null(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        response = await client.patch(URL, json={"timezone": None}, headers=headers)

        assert response.status_code == 422

    async def test_rejects_unknown_timezone(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        response = await client.patch(URL, json={"timezone": "UTC-6"}, headers=headers)

        assert response.status_code == 422

    async def test_currency_cannot_be_changed(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        response = await client.patch(URL, json={"currency": "USD"}, headers=headers)

        assert response.json()["currency"] == "MXN"

    async def test_customer_gets_403(self, client: AsyncClient, session: AsyncSession) -> None:
        headers = await customer_headers(client, session)

        response = await client.patch(URL, json={"buffer_minutes": 15}, headers=headers)

        assert response.status_code == 403

    async def test_anonymous_gets_401(self, client: AsyncClient) -> None:
        response = await client.patch(URL, json={"buffer_minutes": 15})

        assert response.status_code == 401
