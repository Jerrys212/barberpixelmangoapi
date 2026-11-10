import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.users.models import UserRole

Phone = Annotated[str, StringConstraints(pattern=r"^\+[1-9]\d{7,14}$")]
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
