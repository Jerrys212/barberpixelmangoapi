import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.auth import security
from src.config import get_settings
from src.database import get_session, transaction_scope
from src.email.dependencies import get_email_sender
from src.email.sender import OutgoingEmail
from src.main import app
from src.rate_limit import limiter
from src.registry import load_models
from src.users.models import User, UserRole
from src.users.repository import UserRepository

DEFAULT_PASSWORD = "correct-horse-battery"
OTP_PATTERN = re.compile(r"\b(\d{6})\b")


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    async def send(self, email: OutgoingEmail) -> None:
        self.sent.append(email)

    def last_code(self) -> str:
        match = OTP_PATTERN.search(self.sent[-1].body)
        assert match is not None
        return match.group(1)


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = get_settings().test_database_url
    if url is None:
        pytest.exit("TEST_DATABASE_URL no está configurada", returncode=1)
    metadata = load_models().metadata
    test_engine = create_async_engine(url, poolclass=NullPool)
    async with test_engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        db_session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        yield db_session
        await db_session.close()
        await transaction.rollback()


@pytest.fixture
def email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
async def client(
    session: AsyncSession, email_sender: FakeEmailSender
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with transaction_scope(session) as scoped:
            yield scoped

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_email_sender] = lambda: email_sender
    limiter.reset()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def create_user(
    session: AsyncSession,
    *,
    email: str = "cliente@example.com",
    password: str = DEFAULT_PASSWORD,
    role: UserRole = UserRole.CUSTOMER,
    verified: bool = True,
) -> User:
    repo = UserRepository(session)
    user = await repo.create(
        email=email,
        hashed_password=security.hash_password(password),
        full_name="Cliente Prueba",
        phone="5512345678",
        role=role,
    )
    if verified:
        await repo.update(user, {"email_verified_at": user.created_at})
    await session.commit()
    return user


async def login(
    client: AsyncClient,
    email: str = "cliente@example.com",
    password: str = DEFAULT_PASSWORD,
    platform: str = "ANDROID",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "platform": platform},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
