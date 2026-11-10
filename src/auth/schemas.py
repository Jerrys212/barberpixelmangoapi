import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

from src.auth.models import RevokedReason, SessionPlatform
from src.users.schemas import FullName, Phone

Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
OtpCodeStr = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]
DeviceName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password
    full_name: FullName
    phone: Phone


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(max_length=128)]
    platform: SessionPlatform
    device_name: DeviceName | None = None


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, StringConstraints(max_length=256)]


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    session_id: uuid.UUID


class EmailRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: OtpCodeStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: OtpCodeStr
    new_password: Password


class OwnerCreate(BaseModel):
    email: EmailStr
    password: Password
    full_name: FullName
    phone: Phone


class SessionUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user: SessionUserOut
    device_name: str | None
    platform: SessionPlatform
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revoked_reason: RevokedReason | None
    is_active: bool
