import uuid
from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import security
from src.auth.models import EmailVerificationCode, PasswordResetCode, RefreshSession, RevokedReason
from src.auth.repository import OtpRepository
from src.auth.security import OtpPurpose
from src.models import utc_now
from src.users.models import User, UserRole
from tests.conftest import DEFAULT_PASSWORD, FakeEmailSender, create_user, login

VERIFY_URL = "/api/v1/auth/verify-email"
RESEND_URL = "/api/v1/auth/verify-email/resend"
RESET_REQUEST_URL = "/api/v1/auth/password-reset/request"
RESET_CONFIRM_URL = "/api/v1/auth/password-reset/confirm"
EMAIL = "cliente@example.com"
NEW_PASSWORD = "otra-clave-segura"


def _wrong_code(code: str) -> str:
    return "000000" if code != "000000" else "111111"


async def _register(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": EMAIL,
            "password": DEFAULT_PASSWORD,
            "full_name": "Cliente",
            "phone": "+525512345678",
        },
    )
    assert response.status_code == 201


async def _user(session: AsyncSession) -> User:
    session.expire_all()
    return (await session.execute(select(User).where(User.email == EMAIL))).scalar_one()


async def _age_codes(
    session: AsyncSession,
    model: type[EmailVerificationCode] | type[PasswordResetCode],
    *,
    created_seconds_ago: int | None = None,
    expired: bool = False,
) -> None:
    values: dict[str, object] = {}
    if created_seconds_ago is not None:
        values["created_at"] = utc_now() - timedelta(seconds=created_seconds_ago)
    if expired:
        values["expires_at"] = utc_now() - timedelta(seconds=1)
    await session.execute(update(model).values(**values))
    await session.commit()


class TestVerifyEmail:
    async def test_marks_email_as_verified_with_valid_code(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)

        response = await client.post(
            VERIFY_URL, json={"email": EMAIL, "code": email_sender.last_code()}
        )

        assert response.status_code == 204
        assert (await _user(session)).is_email_verified

    async def test_rejects_expired_code(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)
        await _age_codes(session, EmailVerificationCode, expired=True)

        response = await client.post(
            VERIFY_URL, json={"email": EMAIL, "code": email_sender.last_code()}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "OTP_INVALID"
        assert not (await _user(session)).is_email_verified

    async def test_invalidates_code_after_max_attempts(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)
        code = email_sender.last_code()
        for _ in range(5):
            wrong = await client.post(VERIFY_URL, json={"email": EMAIL, "code": _wrong_code(code)})
            assert wrong.status_code == 400

        response = await client.post(VERIFY_URL, json={"email": EMAIL, "code": code})

        assert response.status_code == 400
        assert not (await _user(session)).is_email_verified
        record = (await session.execute(select(EmailVerificationCode))).scalar_one()
        assert record.attempts == 5
        assert record.invalidated_at is not None

    async def test_code_is_single_use(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)
        code = email_sender.last_code()
        assert (
            await client.post(VERIFY_URL, json={"email": EMAIL, "code": code})
        ).status_code == 204

        response = await client.post(VERIFY_URL, json={"email": EMAIL, "code": code})

        assert response.status_code == 400
        record = (await session.execute(select(EmailVerificationCode))).scalar_one()
        assert record.consumed_at is not None

    async def test_new_code_invalidates_previous_one(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)
        old_code = email_sender.last_code()
        await _age_codes(session, EmailVerificationCode, created_seconds_ago=61)
        await client.post(RESEND_URL, json={"email": EMAIL})
        new_code = email_sender.last_code()

        old = await client.post(VERIFY_URL, json={"email": EMAIL, "code": old_code})
        new = await client.post(VERIFY_URL, json={"email": EMAIL, "code": new_code})

        if old_code != new_code:
            assert old.status_code == 400
        assert new.status_code == 204

    async def test_unknown_email_gets_generic_error(self, client: AsyncClient) -> None:
        response = await client.post(
            VERIFY_URL, json={"email": "nadie@example.com", "code": "123456"}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "OTP_INVALID"


class TestResendVerification:
    async def test_ignores_resend_within_cooldown(
        self, client: AsyncClient, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)

        response = await client.post(RESEND_URL, json={"email": EMAIL})

        assert response.status_code == 202
        assert len(email_sender.sent) == 1

    async def test_sends_new_code_after_cooldown(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)
        await _age_codes(session, EmailVerificationCode, created_seconds_ago=61)

        response = await client.post(RESEND_URL, json={"email": EMAIL})

        assert response.status_code == 202
        assert len(email_sender.sent) == 2

    async def test_ignores_sixth_code_in_an_hour(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)
        for _ in range(4):
            await _age_codes(session, EmailVerificationCode, created_seconds_ago=120)
            await client.post(RESEND_URL, json={"email": EMAIL})
        assert len(email_sender.sent) == 5
        await _age_codes(session, EmailVerificationCode, created_seconds_ago=120)

        response = await client.post(RESEND_URL, json={"email": EMAIL})

        assert response.status_code == 202
        assert len(email_sender.sent) == 5

    async def test_unknown_email_gets_same_response_without_email(
        self, client: AsyncClient, email_sender: FakeEmailSender
    ) -> None:
        response = await client.post(RESEND_URL, json={"email": "nadie@example.com"})

        assert response.status_code == 202
        assert email_sender.sent == []


class TestPasswordReset:
    async def test_unknown_email_gets_same_response_without_email(
        self, client: AsyncClient, email_sender: FakeEmailSender
    ) -> None:
        response = await client.post(RESET_REQUEST_URL, json={"email": "nadie@example.com"})

        assert response.status_code == 202
        assert email_sender.sent == []

    async def test_confirm_changes_password_revokes_sessions_and_does_not_log_in(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await create_user(session)
        tokens = await login(client)
        await client.post(RESET_REQUEST_URL, json={"email": EMAIL})

        response = await client.post(
            RESET_CONFIRM_URL,
            json={"email": EMAIL, "code": email_sender.last_code(), "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 204
        assert response.content == b""
        session.expire_all()
        refresh_session = (
            await session.execute(
                select(RefreshSession).where(RefreshSession.id == uuid.UUID(tokens["session_id"]))
            )
        ).scalar_one()
        assert refresh_session.revoked_reason == RevokedReason.PASSWORD_RESET
        old = await client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": DEFAULT_PASSWORD, "platform": "WEB"},
        )
        assert old.status_code == 401
        assert (await login(client, password=NEW_PASSWORD))["access_token"]

    async def test_reset_code_is_single_use(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await create_user(session)
        await client.post(RESET_REQUEST_URL, json={"email": EMAIL})
        payload = {"email": EMAIL, "code": email_sender.last_code(), "new_password": NEW_PASSWORD}
        assert (await client.post(RESET_CONFIRM_URL, json=payload)).status_code == 204

        response = await client.post(
            RESET_CONFIRM_URL, json={**payload, "new_password": "tercera-clave-segura"}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "OTP_INVALID"

    async def test_rejects_expired_reset_code(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await create_user(session)
        await client.post(RESET_REQUEST_URL, json={"email": EMAIL})
        await _age_codes(session, PasswordResetCode, expired=True)

        response = await client.post(
            RESET_CONFIRM_URL,
            json={"email": EMAIL, "code": email_sender.last_code(), "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 400

    async def test_verification_code_cannot_reset_password(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await _register(client)

        response = await client.post(
            RESET_CONFIRM_URL,
            json={"email": EMAIL, "code": email_sender.last_code(), "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 400


class TestOwnerPasswordResetByApi:
    async def test_owner_request_sends_no_code(
        self, client: AsyncClient, session: AsyncSession, email_sender: FakeEmailSender
    ) -> None:
        await create_user(session, email="owner@example.com", role=UserRole.OWNER)

        response = await client.post(RESET_REQUEST_URL, json={"email": "owner@example.com"})

        assert response.status_code == 202
        assert email_sender.sent == []
        assert (await session.execute(select(PasswordResetCode))).first() is None

    async def test_owner_cannot_confirm_reset_even_with_a_valid_code(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        owner = await create_user(session, email="owner@example.com", role=UserRole.OWNER)
        code = "123456"
        await OtpRepository(session, PasswordResetCode).create(
            owner.id,
            security.otp_hmac(OtpPurpose.PASSWORD_RESET, owner.id, code),
            utc_now(),
            utc_now() + timedelta(minutes=10),
        )
        await session.commit()

        response = await client.post(
            RESET_CONFIRM_URL,
            json={"email": "owner@example.com", "code": code, "new_password": NEW_PASSWORD},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "OTP_INVALID"
        assert (await login(client, email="owner@example.com"))["access_token"]


class TestOtpRateLimit:
    async def test_verify_resend_and_reset_are_rate_limited_per_ip(
        self, client: AsyncClient
    ) -> None:
        for url, payload in [
            (VERIFY_URL, {"email": EMAIL, "code": "123456"}),
            (RESEND_URL, {"email": EMAIL}),
            (RESET_REQUEST_URL, {"email": EMAIL}),
        ]:
            for _ in range(10):
                await client.post(url, json=payload)

            response = await client.post(url, json=payload)

            assert response.status_code == 429, url
