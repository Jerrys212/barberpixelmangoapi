from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import bearer, create_user, login

ME_URL = "/api/v1/users/me"


class TestUpdateMe:
    async def test_updates_name_and_phone(self, client: AsyncClient, session: AsyncSession) -> None:
        await create_user(session)
        tokens = await login(client)

        response = await client.patch(
            ME_URL,
            json={"full_name": "Nombre Nuevo", "phone": "+525500001111"},
            headers=bearer(tokens["access_token"]),
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "Nombre Nuevo"
        assert response.json()["phone"] == "+525500001111"

    async def test_rejects_invalid_phone(self, client: AsyncClient, session: AsyncSession) -> None:
        await create_user(session)
        tokens = await login(client)

        response = await client.patch(
            ME_URL, json={"phone": "55-0000-1111"}, headers=bearer(tokens["access_token"])
        )

        assert response.status_code == 422

    async def test_ignores_email_and_role_changes(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)

        response = await client.patch(
            ME_URL,
            json={"email": "otro@example.com", "role": "OWNER"},
            headers=bearer(tokens["access_token"]),
        )

        assert response.status_code == 200
        assert response.json()["email"] == "cliente@example.com"
        assert response.json()["role"] == "CUSTOMER"
