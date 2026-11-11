import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.exceptions import Forbidden
from src.business import service as business_service
from src.catalog.exceptions import ServiceNotFound
from src.catalog.models import Service
from src.catalog.repository import ServiceRepository
from src.catalog.schemas import ServiceCreate, ServiceUpdate
from src.users.models import User, UserRole


def _is_owner(viewer: User | None) -> bool:
    return viewer is not None and viewer.role == UserRole.OWNER


async def list_services(
    session: AsyncSession, viewer: User | None, *, include_inactive: bool
) -> Sequence[Service]:
    if include_inactive and not _is_owner(viewer):
        raise Forbidden()
    return await ServiceRepository(session).list(include_inactive=include_inactive)


async def get_service(session: AsyncSession, service_id: uuid.UUID, viewer: User | None) -> Service:
    service = await ServiceRepository(session).get(service_id)
    if service is None or (not service.is_active and not _is_owner(viewer)):
        raise ServiceNotFound()
    return service


async def get_bookable_service(session: AsyncSession, service_id: uuid.UUID) -> Service:
    return await get_service(session, service_id, viewer=None)


async def create_service(session: AsyncSession, data: ServiceCreate) -> Service:
    profile = await business_service.get_profile(session)
    return await ServiceRepository(session).create(
        {**data.model_dump(), "currency": profile.currency}
    )


async def update_service(
    session: AsyncSession, service_id: uuid.UUID, data: ServiceUpdate
) -> Service:
    repo = ServiceRepository(session)
    service = await repo.get(service_id)
    if service is None:
        raise ServiceNotFound()
    return await repo.update(service, data.changes())
