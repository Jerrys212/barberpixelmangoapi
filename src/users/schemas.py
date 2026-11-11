import re
import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from src.users.models import UserRole

PHONE_PATTERN = re.compile(r"[0-9]{10}")


def _validate_phone(value: str) -> str:
    if not PHONE_PATTERN.fullmatch(value):
        raise ValueError("El teléfono debe tener exactamente 10 dígitos, solo números")
    return value


Phone = Annotated[str, AfterValidator(_validate_phone)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    phone: str
    role: UserRole
    is_email_verified: bool


class UserUpdate(BaseModel):
    full_name: FullName | None = None
    phone: Phone | None = Field(default=None)
