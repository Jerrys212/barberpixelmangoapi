import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.models import Service


class ServiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, include_inactive: bool) -> Sequence[Service]:
        query = select(Service).order_by(Service.name, Service.id)
        if not include_inactive:
            query = query.where(Service.is_active.is_(True))
        return (await self.session.execute(query)).scalars().all()

    async def get(self, service_id: uuid.UUID) -> Service | None:
        return await self.session.get(Service, service_id)

    async def create(self, values: dict[str, Any]) -> Service:
        service = Service(**values)
        self.session.add(service)
        await self.session.flush()
        return service

    async def update(self, service: Service, values: dict[str, Any]) -> Service:
        for field, value in values.items():
            setattr(service, field, value)
        await self.session.flush()
        return service
