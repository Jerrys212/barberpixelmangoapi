from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.business.models import BusinessProfile


class BusinessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, *, for_update: bool = False) -> BusinessProfile:
        query = select(BusinessProfile)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        profile = (await self.session.execute(query)).scalar_one_or_none()
        if profile is not None:
            return profile
        await self.session.execute(
            insert(BusinessProfile).values().on_conflict_do_nothing(index_elements=["singleton"])
        )
        return (await self.session.execute(query)).scalar_one()

    async def update(self, profile: BusinessProfile, values: dict[str, Any]) -> BusinessProfile:
        for field, value in values.items():
            setattr(profile, field, value)
        await self.session.flush()
        return profile
