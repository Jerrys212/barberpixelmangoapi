from fastapi import APIRouter

from src.database import SessionDep
from src.health import service as health_service
from src.health.schemas import HealthOut

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthOut)
async def read_health(session: SessionDep) -> HealthOut:
    return await health_service.check(session)
