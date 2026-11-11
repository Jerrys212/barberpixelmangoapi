import asyncio
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.auth import security
from src.auth.models import EmailVerificationCode
from src.database import get_session, transaction_scope
from src.email.dependencies import get_email_sender
from src.email.sender import OutgoingEmail
from src.main import app
from src.rate_limit import limiter
from src.users.models import User, UserRole
from src.users.repository import UserRepository
from tests.conftest import DEFAULT_PASSWORD, FakeEmailSender

EMAIL = "concurrente@example.com"


@pytest.fixture
async def factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session, transaction_scope(session) as scoped:
            yield scoped

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_email_sender] = FakeEmailSender
    limiter.reset()
    yield session_factory
    app.dependency_overrides.clear()
    async with session_factory() as session:
        await session.execute(delete(User).where(User.email == EMAIL))
        await session.commit()


async def _create_committed_user(
    session_factory: async_sessionmaker[AsyncSession], *, verified: bool
) -> None:
    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.create(
            email=EMAIL,
            hashed_password=security.hash_password(DEFAULT_PASSWORD),
            full_name="Concurrente",
            phone="5512345678",
            role=UserRole.CUSTOMER,
        )
        if verified:
            await repo.update(user, {"email_verified_at": user.created_at})
        await session.commit()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestConcurrentLimits:
    async def test_parallel_wrong_passwords_still_lock_the_account(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _create_committed_user(factory, verified=True)
        payload = {"email": EMAIL, "password": "incorrecta", "platform": "WEB"}

        async with await _client() as http:
            responses = await asyncio.gather(
                *(http.post("/api/v1/auth/login", json=payload) for _ in range(8))
            )

        assert all(response.status_code == 401 for response in responses)
        async with factory() as session:
            user = (await session.execute(select(User).where(User.email == EMAIL))).scalar_one()
            assert user.locked_until is not None

    async def test_parallel_resends_issue_a_single_code(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _create_committed_user(factory, verified=False)

        async with await _client() as http:
            responses = await asyncio.gather(
                *(
                    http.post("/api/v1/auth/verify-email/resend", json={"email": EMAIL})
                    for _ in range(6)
                )
            )

        assert all(response.status_code == 202 for response in responses)
        async with factory() as session:
            issued = await session.execute(
                select(func.count())
                .select_from(EmailVerificationCode)
                .join(User, User.id == EmailVerificationCode.user_id)
                .where(User.email == EMAIL)
            )
            assert issued.scalar_one() == 1


class TestCommitOrdering:
    async def test_verification_email_is_sent_after_the_code_is_committed(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> None:
        committed_when_sent: list[int] = []

        class CommitCheckingSender:
            async def send(self, email: OutgoingEmail) -> None:
                async with factory() as observer:
                    count = await observer.execute(
                        select(func.count())
                        .select_from(EmailVerificationCode)
                        .join(User, User.id == EmailVerificationCode.user_id)
                        .where(User.email == EMAIL)
                    )
                    committed_when_sent.append(count.scalar_one())

        app.dependency_overrides[get_email_sender] = CommitCheckingSender

        async with await _client() as http:
            response = await http.post(
                "/api/v1/auth/register",
                json={
                    "email": EMAIL,
                    "password": DEFAULT_PASSWORD,
                    "full_name": "Concurrente",
                    "phone": "5512345678",
                },
            )

        assert response.status_code == 201
        assert committed_when_sent == [1]
