from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "BarberPixelMango API"
    environment: Environment = Environment.LOCAL
    database_url: str
    test_database_url: str | None = None
    cors_origins: list[str] = []
    rate_limit_storage_uri: str = "memory://"
    rate_limit_auth: str = "10/minute"

    @property
    def docs_enabled(self) -> bool:
        return self.environment != Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
