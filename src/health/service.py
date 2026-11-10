from sqlalchemy.ext.asyncio import AsyncSession

from src.health.repository import HealthRepository
from src.health.schemas import HealthOut, HealthStatus


async def check(session: AsyncSession) -> HealthOut:
    await HealthRepository(session).ping()
    return HealthOut(status=HealthStatus.OK, database=HealthStatus.OK)
