import uuid
from datetime import timedelta

import jwt
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.models import AuditAction, AuditLog
from src.auth import security
from src.auth.config import get_auth_settings
from src.auth.models import RefreshSession, RefreshToken, RevokedReason
from src.models import utc_now
from src.users.models import UserRole
from tests.conftest import bearer, create_user, login

ME_URL = "/api/v1/users/me"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
SESSIONS_URL = "/api/v1/auth/sessions"


async def _get_session(session: AsyncSession, session_id: str) -> RefreshSession:
    session.expire_all()
    result = await session.execute(
        select(RefreshSession).where(RefreshSession.id == uuid.UUID(session_id))
    )
    return result.scalar_one()


async def _age_rotation(session: AsyncSession, raw_token: str, seconds: int) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == security.hash_refresh_token(raw_token))
        .values(rotated_at=utc_now() - timedelta(seconds=seconds))
    )
    await session.commit()


class TestProtectedEndpoint:
    async def test_rejects_request_without_token(self, client: AsyncClient) -> None:
        response = await client.get(ME_URL)

        assert response.status_code == 401
        assert response.json()["code"] == "NOT_AUTHENTICATED"
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_accepts_valid_access_token(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)

        response = await client.get(ME_URL, headers=bearer(tokens["access_token"]))

        assert response.status_code == 200
        assert response.json()["email"] == "cliente@example.com"

    async def test_rejects_expired_access_token(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session)
        tokens = await login(client)
        settings = get_auth_settings()
        past = utc_now() - timedelta(minutes=30)
        expired = jwt.encode(
            {
                "sub": str(user.id),
                "sid": tokens["session_id"],
                "role": "CUSTOMER",
                "type": "access",
                "iat": past,
                "exp": past + timedelta(minutes=15),
                "jti": "x",
            },
            settings.auth_secret_key.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )

        response = await client.get(ME_URL, headers=bearer(expired))

        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_TOKEN"

    async def test_rejects_refresh_token_used_as_access_token(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)

        response = await client.get(ME_URL, headers=bearer(tokens["refresh_token"]))

        assert response.status_code == 401

    async def test_rejects_access_token_with_wrong_type_claim(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        user = await create_user(session)
        tokens = await login(client)
        settings = get_auth_settings()
        now = utc_now()
        forged = jwt.encode(
            {
                "sub": str(user.id),
                "sid": tokens["session_id"],
                "type": "refresh",
                "iat": now,
                "exp": now + timedelta(minutes=5),
            },
            settings.auth_secret_key.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )

        response = await client.get(ME_URL, headers=bearer(forged))

        assert response.status_code == 401

    async def test_rejects_access_token_of_revoked_session(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)
        await client.post(LOGOUT_URL, headers=bearer(tokens["access_token"]))

        response = await client.get(ME_URL, headers=bearer(tokens["access_token"]))

        assert response.status_code == 401
        assert response.json()["code"] == "SESSION_REVOKED"


class TestRefresh:
    async def test_rotates_refresh_token(self, client: AsyncClient, session: AsyncSession) -> None:
        await create_user(session)
        tokens = await login(client)

        response = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

        assert response.status_code == 200
        new_tokens = response.json()
        assert new_tokens["refresh_token"] != tokens["refresh_token"]
        assert new_tokens["session_id"] == tokens["session_id"]
        me = await client.get(ME_URL, headers=bearer(new_tokens["access_token"]))
        assert me.status_code == 200

    async def test_rejects_unknown_refresh_token(self, client: AsyncClient) -> None:
        response = await client.post(REFRESH_URL, json={"refresh_token": "no-existe"})

        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_TOKEN"

    async def test_reuse_of_rotated_token_after_grace_revokes_session(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)
        rotated = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
        await _age_rotation(session, tokens["refresh_token"], seconds=31)

        reuse = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

        assert reuse.status_code == 401
        assert reuse.json()["code"] == "SESSION_REVOKED"
        refresh_session = await _get_session(session, tokens["session_id"])
        assert refresh_session.revoked_reason == RevokedReason.REUSE_DETECTED
        latest = await client.post(
            REFRESH_URL, json={"refresh_token": rotated.json()["refresh_token"]}
        )
        assert latest.status_code == 401

    async def test_concurrent_refresh_within_grace_does_not_revoke(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)
        first = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

        second = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

        assert first.status_code == 200
        assert second.status_code == 200
        assert (await _get_session(session, tokens["session_id"])).revoked_at is None
        follow_up = await client.post(
            REFRESH_URL, json={"refresh_token": second.json()["refresh_token"]}
        )
        assert follow_up.status_code == 200

    async def test_reuse_of_older_token_within_grace_revokes_session(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)
        first = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
        await client.post(REFRESH_URL, json={"refresh_token": first.json()["refresh_token"]})

        reuse = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

        assert reuse.status_code == 401
        refresh_session = await _get_session(session, tokens["session_id"])
        assert refresh_session.revoked_reason == RevokedReason.REUSE_DETECTED

    async def test_rejects_refresh_of_expired_session(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.id == uuid.UUID(tokens["session_id"]))
            .values(expires_at=utc_now() - timedelta(seconds=1))
        )
        await session.commit()

        response = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

        assert response.status_code == 401


class TestLogout:
    async def test_revokes_current_session(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)

        response = await client.post(LOGOUT_URL, headers=bearer(tokens["access_token"]))

        assert response.status_code == 204
        refresh_session = await _get_session(session, tokens["session_id"])
        assert refresh_session.revoked_reason == RevokedReason.LOGOUT
        refresh = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
        assert refresh.status_code == 401

    async def test_keeps_other_sessions_of_user_active(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        phone = await login(client, platform="ANDROID")
        browser = await login(client, platform="WEB")

        await client.post(LOGOUT_URL, headers=bearer(phone["access_token"]))

        assert (
            await client.get(ME_URL, headers=bearer(browser["access_token"]))
        ).status_code == 200


class TestOwnerSessions:
    async def test_customer_cannot_list_sessions(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session)
        tokens = await login(client)

        response = await client.get(SESSIONS_URL, headers=bearer(tokens["access_token"]))

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"

    async def test_owner_lists_active_sessions_with_user_data(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session, email="owner@example.com", role=UserRole.OWNER)
        customer = await create_user(session)
        await login(client, platform="IOS")
        owner = await login(client, email="owner@example.com")

        response = await client.get(
            SESSIONS_URL,
            params={"user_id": str(customer.id)},
            headers=bearer(owner["access_token"]),
        )

        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 1
        assert sessions[0]["platform"] == "IOS"
        assert sessions[0]["user"]["email"] == "cliente@example.com"
        assert sessions[0]["is_active"] is True

    async def test_revoking_one_session_keeps_the_others(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session, email="owner@example.com", role=UserRole.OWNER)
        await create_user(session)
        phone = await login(client, platform="ANDROID")
        browser = await login(client, platform="WEB")
        owner = await login(client, email="owner@example.com")

        response = await client.delete(
            f"{SESSIONS_URL}/{phone['session_id']}", headers=bearer(owner["access_token"])
        )

        assert response.status_code == 204
        assert (await client.get(ME_URL, headers=bearer(phone["access_token"]))).status_code == 401
        assert (
            await client.get(ME_URL, headers=bearer(browser["access_token"]))
        ).status_code == 200
        browser_refresh = await client.post(
            REFRESH_URL, json={"refresh_token": browser["refresh_token"]}
        )
        assert browser_refresh.status_code == 200
        phone_refresh = await client.post(
            REFRESH_URL, json={"refresh_token": phone["refresh_token"]}
        )
        assert phone_refresh.status_code == 401
        revoked = await _get_session(session, phone["session_id"])
        assert revoked.revoked_reason == RevokedReason.OWNER_REVOKED

    async def test_revoking_a_session_is_audited(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        owner_user = await create_user(session, email="owner@example.com", role=UserRole.OWNER)
        await create_user(session)
        phone = await login(client)
        owner = await login(client, email="owner@example.com")

        await client.delete(
            f"{SESSIONS_URL}/{phone['session_id']}", headers=bearer(owner["access_token"])
        )

        result = await session.execute(select(AuditLog))
        entry = result.scalar_one()
        assert entry.action == AuditAction.SESSION_REVOKED
        assert entry.actor_user_id == owner_user.id
        assert str(entry.target_id) == phone["session_id"]

    async def test_revoke_unknown_session_returns_404(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session, email="owner@example.com", role=UserRole.OWNER)
        owner = await login(client, email="owner@example.com")

        response = await client.delete(
            f"{SESSIONS_URL}/{uuid.uuid4()}", headers=bearer(owner["access_token"])
        )

        assert response.status_code == 404
        assert response.json()["code"] == "SESSION_NOT_FOUND"

    async def test_owner_revokes_all_sessions_of_a_user(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await create_user(session, email="owner@example.com", role=UserRole.OWNER)
        customer = await create_user(session)
        phone = await login(client, platform="ANDROID")
        browser = await login(client, platform="WEB")
        owner = await login(client, email="owner@example.com")

        response = await client.delete(
            f"/api/v1/auth/users/{customer.id}/sessions", headers=bearer(owner["access_token"])
        )

        assert response.status_code == 204
        assert (await client.get(ME_URL, headers=bearer(phone["access_token"]))).status_code == 401
        assert (
            await client.get(ME_URL, headers=bearer(browser["access_token"]))
        ).status_code == 401
        assert (await client.get(ME_URL, headers=bearer(owner["access_token"]))).status_code == 200
