import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth import service as auth_service
from src.auth.exceptions import EmailNotVerified, Forbidden, NotAuthenticated
from src.auth.security import decode_access_token
from src.auth.service import ClientInfo
from src.database import SessionDep
from src.users.models import User, UserRole

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise NotAuthenticated()
    return await auth_service.get_authenticated_user(session, credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    if credentials is None:
        return None
    return await auth_service.get_authenticated_user(session, credentials.credentials)


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_current_session_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    _: CurrentUser,
) -> uuid.UUID:
    if credentials is None:
        raise NotAuthenticated()
    return decode_access_token(credentials.credentials).session_id


CurrentSessionId = Annotated[uuid.UUID, Depends(get_current_session_id)]


def require_owner(user: CurrentUser) -> User:
    if user.role != UserRole.OWNER:
        raise Forbidden()
    return user


def require_verified_customer(user: CurrentUser) -> User:
    if user.role != UserRole.CUSTOMER:
        raise Forbidden()
    if not user.is_email_verified:
        raise EmailNotVerified()
    return user


OwnerUser = Annotated[User, Depends(require_owner)]
VerifiedCustomer = Annotated[User, Depends(require_verified_customer)]


def get_client_info(request: Request) -> ClientInfo:
    return ClientInfo(
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


ClientInfoDep = Annotated[ClientInfo, Depends(get_client_info)]
