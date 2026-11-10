from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_secret_key: SecretStr = Field(min_length=32)
    otp_hmac_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    refresh_reuse_grace_seconds: int = 30
    otp_expire_minutes: int = 10
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_max_resends_per_hour: int = 5
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
