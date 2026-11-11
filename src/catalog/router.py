import uuid
from collections.abc import Sequence

from fastapi import APIRouter, status

from src.auth.dependencies import OptionalUser, OwnerUser
from src.catalog import service as catalog_service
from src.catalog.models import Service
from src.catalog.schemas import ServiceCreate, ServiceOut, ServiceUpdate
from src.database import SessionDep

router = APIRouter(prefix="/services", tags=["catalog"])


@router.get("", response_model=list[ServiceOut])
async def list_services(
    session: SessionDep, viewer: OptionalUser, include_inactive: bool = False
) -> Sequence[Service]:
    return await catalog_service.list_services(session, viewer, include_inactive=include_inactive)


@router.get("/{service_id}", response_model=ServiceOut)
async def read_service(service_id: uuid.UUID, session: SessionDep, viewer: OptionalUser) -> Service:
    return await catalog_service.get_service(session, service_id, viewer)


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(data: ServiceCreate, _: OwnerUser, session: SessionDep) -> Service:
    return await catalog_service.create_service(session, data)


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    service_id: uuid.UUID, data: ServiceUpdate, _: OwnerUser, session: SessionDep
) -> Service:
    return await catalog_service.update_service(session, service_id, data)
