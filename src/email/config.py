from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailBackend(StrEnum):
    CONSOLE = "console"
    SMTP = "smtp"


class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    email_backend: EmailBackend = EmailBackend.CONSOLE
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: SecretStr | None = None
    smtp_from: str | None = None
    smtp_timeout_seconds: float = 10.0

    @model_validator(mode="after")
    def require_smtp_settings(self) -> Self:
        if self.email_backend == EmailBackend.SMTP:
            required = {
                "SMTP_HOST": self.smtp_host,
                "SMTP_USER": self.smtp_user,
                "SMTP_PASS": self.smtp_pass,
                "SMTP_FROM": self.smtp_from,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"EMAIL_BACKEND=smtp requiere: {', '.join(missing)}")
        return self


@lru_cache
def get_email_settings() -> EmailSettings:
    return EmailSettings()
