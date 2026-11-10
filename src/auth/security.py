import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import jwt
from pwdlib import PasswordHash

from src.auth.config import get_auth_settings

ACCESS_TOKEN_TYPE = "access"  # noqa: S105
_password_hash = PasswordHash.recommended()
# Verified against when the user does not exist, so both paths take similar time.
_DUMMY_PASSWORD_HASH = _password_hash.hash(secrets.token_urlsafe(16))


class OtpPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"  # noqa: S105


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID


class InvalidAccessToken(Exception):
    pass


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str | None) -> bool:
    if hashed_password is None:
        _password_hash.verify(password, _DUMMY_PASSWORD_HASH)
        return False
    return _password_hash.verify(password, hashed_password)


def create_access_token(
    user_id: uuid.UUID, session_id: uuid.UUID, role: str, now: datetime
) -> tuple[str, int]:
    settings = get_auth_settings()
    expires_in = settings.access_token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(
        payload, settings.auth_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, expires_in


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_auth_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "sid", "type"]},
        )
        if payload["type"] != ACCESS_TOKEN_TYPE:
            raise InvalidAccessToken
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]), session_id=uuid.UUID(payload["sid"])
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidAccessToken from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_otp() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def otp_hmac(purpose: OtpPurpose, user_id: uuid.UUID, code: str) -> str:
    key = get_auth_settings().otp_hmac_secret.get_secret_value().encode()
    message = f"{purpose.value}:{user_id}:{code}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def otp_matches(expected_hmac: str, purpose: OtpPurpose, user_id: uuid.UUID, code: str) -> bool:
    return hmac.compare_digest(expected_hmac, otp_hmac(purpose, user_id, code))
