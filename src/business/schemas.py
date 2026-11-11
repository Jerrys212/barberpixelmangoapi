from functools import lru_cache
from typing import Annotated, ClassVar
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from src.schemas import PatchModel
from src.users.schemas import Phone


@lru_cache
def _timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def _validate_timezone(value: str) -> str:
    if value not in _timezones():
        raise ValueError("Zona horaria IANA desconocida")
    return value


Timezone = Annotated[str, AfterValidator(_validate_timezone)]
BusinessName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    phone: str | None
    address: str | None
    timezone: str
    currency: str
    slot_interval_minutes: int
    buffer_minutes: int
    hold_minutes: int
    cancellation_window_minutes: int
    min_notice_minutes: int
    booking_horizon_days: int


class BusinessUpdate(PatchModel):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"phone", "address"})

    name: BusinessName | None = None
    phone: Phone | None = None
    address: Address | None = None
    timezone: Timezone | None = None
    slot_interval_minutes: int | None = Field(default=None, ge=5, le=60)
    buffer_minutes: int | None = Field(default=None, ge=0, le=120)
    hold_minutes: int | None = Field(default=None, ge=5, le=60)
    cancellation_window_minutes: int | None = Field(default=None, ge=0, le=10080)
    min_notice_minutes: int | None = Field(default=None, ge=0, le=10080)
    booking_horizon_days: int | None = Field(default=None, ge=1, le=365)
