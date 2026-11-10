from httpx import AsyncClient


class TestReadHealth:
    async def test_returns_ok_when_database_is_reachable(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
