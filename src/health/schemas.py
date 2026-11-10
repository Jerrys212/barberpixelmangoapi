from enum import StrEnum

from pydantic import BaseModel


class HealthStatus(StrEnum):
    OK = "ok"


class HealthOut(BaseModel):
    status: HealthStatus
    database: HealthStatus
