from fastapi import APIRouter

from src.auth.dependencies import ClientInfoDep, OwnerUser
from src.business import service as business_service
from src.business.models import BusinessProfile
from src.business.schemas import BusinessOut, BusinessUpdate
from src.database import SessionDep

router = APIRouter(prefix="/business", tags=["business"])


@router.get("", response_model=BusinessOut)
async def read_business(session: SessionDep) -> BusinessProfile:
    return await business_service.get_profile(session)


@router.patch("", response_model=BusinessOut)
async def update_business(
    data: BusinessUpdate, owner: OwnerUser, session: SessionDep, client: ClientInfoDep
) -> BusinessProfile:
    return await business_service.update_profile(session, owner, data, client)
