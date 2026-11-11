from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import customer_headers, owner_headers

URL = "/api/v1/services"
HAIRCUT = {
    "name": "Corte clásico",
    "description": "Corte con máquina y tijera",
    "price_cents": 25000,
    "duration_minutes": 30,
    "image_url": "https://cdn.example.com/corte.jpg",
}


async def create_service(
    client: AsyncClient, headers: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    response = await client.post(URL, json={**HAIRCUT, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


class TestCreateService:
    async def test_owner_creates_service_with_business_currency(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        body = await create_service(client, headers, currency="USD")

        assert body["currency"] == "MXN"
        assert body["price_cents"] == 25000
        assert body["is_active"] is True

    async def test_rejects_non_https_image(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        response = await client.post(
            URL, json={**HAIRCUT, "image_url": "http://cdn.example.com/a.jpg"}, headers=headers
        )

        assert response.status_code == 422

    async def test_rejects_negative_price_and_zero_duration(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)

        negative = await client.post(URL, json={**HAIRCUT, "price_cents": -1}, headers=headers)
        zero = await client.post(URL, json={**HAIRCUT, "duration_minutes": 0}, headers=headers)

        assert negative.status_code == zero.status_code == 422

    async def test_customer_gets_403(self, client: AsyncClient, session: AsyncSession) -> None:
        headers = await customer_headers(client, session)

        response = await client.post(URL, json=HAIRCUT, headers=headers)

        assert response.status_code == 403


class TestListServices:
    async def test_public_list_hides_inactive_services(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        await create_service(client, headers)
        inactive = await create_service(client, headers, name="Barba")
        await client.patch(f"{URL}/{inactive['id']}", json={"is_active": False}, headers=headers)

        response = await client.get(URL)

        assert [s["name"] for s in response.json()] == ["Corte clásico"]

    async def test_owner_sees_inactive_with_flag(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        await create_service(client, headers)
        inactive = await create_service(client, headers, name="Barba")
        await client.patch(f"{URL}/{inactive['id']}", json={"is_active": False}, headers=headers)

        response = await client.get(URL, params={"include_inactive": "true"}, headers=headers)

        assert {s["name"] for s in response.json()} == {"Corte clásico", "Barba"}

    async def test_include_inactive_as_anonymous_gets_403(self, client: AsyncClient) -> None:
        response = await client.get(URL, params={"include_inactive": "true"})

        assert response.status_code == 403

    async def test_include_inactive_as_customer_gets_403(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await customer_headers(client, session)

        response = await client.get(URL, params={"include_inactive": "true"}, headers=headers)

        assert response.status_code == 403


class TestReadService:
    async def test_inactive_service_is_404_for_public_but_visible_to_owner(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        service = await create_service(client, headers)
        await client.patch(f"{URL}/{service['id']}", json={"is_active": False}, headers=headers)

        public = await client.get(f"{URL}/{service['id']}")
        owner = await client.get(f"{URL}/{service['id']}", headers=headers)

        assert public.status_code == 404
        assert public.json()["code"] == "SERVICE_NOT_FOUND"
        assert owner.status_code == 200


class TestUpdateService:
    async def test_owner_edits_fields(self, client: AsyncClient, session: AsyncSession) -> None:
        headers = await owner_headers(client, session)
        service = await create_service(client, headers)

        response = await client.patch(
            f"{URL}/{service['id']}",
            json={"price_cents": 30000, "image_url": None},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["price_cents"] == 30000
        assert response.json()["image_url"] is None

    async def test_rejects_null_on_required_field(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        headers = await owner_headers(client, session)
        service = await create_service(client, headers)

        response = await client.patch(
            f"{URL}/{service['id']}", json={"name": None}, headers=headers
        )

        assert response.status_code == 422

    async def test_unknown_service_is_404(self, client: AsyncClient, session: AsyncSession) -> None:
        headers = await owner_headers(client, session)

        response = await client.patch(
            f"{URL}/00000000-0000-0000-0000-000000000000", json={"name": "X"}, headers=headers
        )

        assert response.status_code == 404
