import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import service as auth_service
from src.auth.dependencies import require_owner, require_verified_customer
from src.auth.exceptions import EmailNotVerified, Forbidden
from src.auth.schemas import OwnerCreate
from src.users.exceptions import OwnerAlreadyExists, OwnerNotFound
from src.users.models import UserRole
from tests.conftest import bearer, create_user, login

OWNER_DATA = OwnerCreate(
    email="Dueno@Example.com",
    password="clave-del-dueno",
    full_name="Dueño",
    phone="+525599998888",
)


class TestCreateOwner:
    async def test_creates_verified_owner(self, session: AsyncSession) -> None:
        owner = await auth_service.create_owner(session, OWNER_DATA)

        assert owner.role == UserRole.OWNER
        assert owner.email == "dueno@example.com"
        assert owner.is_email_verified

    async def test_rejects_second_owner(self, session: AsyncSession) -> None:
        await auth_service.create_owner(session, OWNER_DATA)

        with pytest.raises(OwnerAlreadyExists):
            await auth_service.create_owner(
                session, OWNER_DATA.model_copy(update={"email": "otro@example.com"})
            )


class TestResetOwnerPassword:
    async def test_changes_password_and_revokes_owner_sessions(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await auth_service.create_owner(session, OWNER_DATA)
        await session.commit()
        tokens = await login(client, email="dueno@example.com", password="clave-del-dueno")

        await auth_service.reset_owner_password(session, "nueva-clave-dueno")
        await session.commit()

        me = await client.get("/api/v1/users/me", headers=bearer(tokens["access_token"]))
        assert me.status_code == 401
        assert (await login(client, email="dueno@example.com", password="nueva-clave-dueno"))[
            "access_token"
        ]

    async def test_fails_when_no_owner_exists(self, session: AsyncSession) -> None:
        with pytest.raises(OwnerNotFound):
            await auth_service.reset_owner_password(session, "nueva-clave-dueno")


class TestRoleDependencies:
    async def test_unverified_customer_gets_email_not_verified(self, session: AsyncSession) -> None:
        user = await create_user(session, verified=False)

        with pytest.raises(EmailNotVerified) as exc_info:
            require_verified_customer(user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "EMAIL_NOT_VERIFIED"

    async def test_verified_customer_passes(self, session: AsyncSession) -> None:
        user = await create_user(session)

        assert require_verified_customer(user) is user

    async def test_owner_is_not_a_customer(self, session: AsyncSession) -> None:
        owner = await create_user(session, email="owner@example.com", role=UserRole.OWNER)

        with pytest.raises(Forbidden):
            require_verified_customer(owner)

    async def test_customer_is_not_owner(self, session: AsyncSession) -> None:
        user = await create_user(session)

        with pytest.raises(Forbidden):
            require_owner(user)
