import uuid
from typing import Annotated, ClassVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    PlainSerializer,
    StringConstraints,
)

from src.schemas import PatchModel


def _require_https(value: HttpUrl) -> HttpUrl:
    if value.scheme != "https":
        raise ValueError("La imagen debe ser una URL https")
    return value


ImageUrl = Annotated[
    HttpUrl,
    AfterValidator(_require_https),
    PlainSerializer(str, return_type=str),
]
ServiceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
PriceCents = Annotated[int, Field(ge=0, le=100_000_000)]
DurationMinutes = Annotated[int, Field(ge=1, le=480)]


class ServiceCreate(BaseModel):
    name: ServiceName
    description: Description | None = None
    price_cents: PriceCents
    duration_minutes: DurationMinutes
    image_url: ImageUrl | None = None


class ServiceUpdate(PatchModel):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"description", "image_url"})

    name: ServiceName | None = None
    description: Description | None = None
    price_cents: PriceCents | None = None
    duration_minutes: DurationMinutes | None = None
    image_url: ImageUrl | None = None
    is_active: bool | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    price_cents: int
    currency: str
    duration_minutes: int
    image_url: str | None
    is_active: bool
