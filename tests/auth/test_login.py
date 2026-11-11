from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import utc_now
from src.users.models import User, UserRole
from tests.conftest import DEFAULT_PASSWORD, FakeEmailSender, create_user, login

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REGISTER_PAYLOAD = {
    "email": "Nuevo@Example.com",
    "password": DEFAULT_PASSWORD,
    "full_name": "Nuevo Cliente",
    "phone": "5511112222",
}


async def _get_user(session: AsyncSession, email: str) -> User:
    session.expire_all()
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one()


class TestRegister:
    async def test_creates_unverified_customer_and_sends_code(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        response = await client.post(REGISTER_URL, json=REGISTER_PAYLOAD)

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "nuevo@example.com"
        assert body["role"] == "CUSTOMER"
        assert body["is_email_verified"] is False
        assert "access_token" not in body
        assert "hashed_password" not in body
        assert len(email_sender.sent) == 1
        assert email_sender.sent[0].to == "nuevo@example.com"

    async def test_ignores_role_in_payload(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        response = await client.post(REGISTER_URL, json={**REGISTER_PAYLOAD, "role": "OWNER"})

        assert response.status_code == 201
        assert response.json()["role"] == "CUSTOMER"
        assert (await _get_user(session, "nuevo@example.com")).role == UserRole.CUSTOMER

    async def test_rejects_duplicate_email(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session, email="nuevo@example.com")

        response = await client.post(REGISTER_URL, json=REGISTER_PAYLOAD)

        assert response.status_code == 409
        assert response.json()["code"] == "EMAIL_ALREADY_REGISTERED"

    @pytest.mark.parametrize(
        "phone",
        ["551111222", "55111122223", "+525511112222", "55-1111-2222", "55 1111 2222", "55111a2222"],
    )
    async def test_rejects_phone_that_is_not_exactly_ten_digits(
        self, client: AsyncClient, phone: str
    ) -> None:
        response = await client.post(REGISTER_URL, json={**REGISTER_PAYLOAD, "phone": phone})

        assert response.status_code == 422
        assert "10 dígitos" in response.json()["detail"][0]["msg"]

    async def test_rejects_short_password(self, client: AsyncClient) -> None:
        response = await client.post(REGISTER_URL, json={**REGISTER_PAYLOAD, "password": "corta"})

        assert response.status_code == 422


class TestLogin:
    async def test_returns_token_pair_with_valid_credentials(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)

        body = await login(client)

        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 15 * 60
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["session_id"]

    async def test_unverified_user_can_login(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session, verified=False)

        body = await login(client)

        assert body["access_token"]

    async def test_wrong_password_and_unknown_user_get_identical_response(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)

        wrong_password = await client.post(
            LOGIN_URL,
            json={"email": "cliente@example.com", "password": "incorrecta", "platform": "IOS"},
        )
        unknown_user = await client.post(
            LOGIN_URL,
            json={"email": "nadie@example.com", "password": "incorrecta", "platform": "IOS"},
        )

        assert wrong_password.status_code == unknown_user.status_code == 401
        assert wrong_password.json() == unknown_user.json()
        assert wrong_password.json()["code"] == "INVALID_CREDENTIALS"
        assert wrong_password.headers["www-authenticate"] == "Bearer"
        assert unknown_user.headers["www-authenticate"] == "Bearer"

    async def test_locks_account_after_five_failed_attempts(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        bad = {"email": "cliente@example.com", "password": "incorrecta", "platform": "WEB"}
        for _ in range(5):
            assert (await client.post(LOGIN_URL, json=bad)).status_code == 401

        locked = await client.post(LOGIN_URL, json={**bad, "password": DEFAULT_PASSWORD})
        unknown = await client.post(LOGIN_URL, json={**bad, "email": "nadie@example.com"})

        assert locked.status_code == 401
        assert locked.json() == unknown.json()
        user = await _get_user(session, "cliente@example.com")
        assert user.locked_until is not None
        assert user.locked_until > utc_now() + timedelta(minutes=14)

    async def test_allows_login_after_lockout_expires(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session)
        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(locked_until=utc_now() - timedelta(seconds=1))
        )
        await session.commit()

        body = await login(client)

        assert body["access_token"]
        assert (await _get_user(session, "cliente@example.com")).locked_until is None

    async def test_successful_login_resets_failed_attempts(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        bad = {"email": "cliente@example.com", "password": "incorrecta", "platform": "WEB"}
        for _ in range(3):
            await client.post(LOGIN_URL, json=bad)

        await login(client)

        assert (await _get_user(session, "cliente@example.com")).failed_login_attempts == 0

    async def test_rate_limits_after_ten_requests_per_minute(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        bad = {"email": "nadie@example.com", "password": "incorrecta", "platform": "WEB"}
        for _ in range(10):
            assert (await client.post(LOGIN_URL, json=bad)).status_code == 401

        response = await client.post(LOGIN_URL, json=bad)

        assert response.status_code == 429
        assert response.json()["code"] == "RATE_LIMITED"
