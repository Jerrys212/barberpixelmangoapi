import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from src.availability import service as availability_service
from src.availability.schemas import AvailabilityOut
from src.database import SessionDep

router = APIRouter(prefix="/availability", tags=["availability"])


@router.get("", response_model=AvailabilityOut)
async def read_availability(
    session: SessionDep,
    service_id: Annotated[uuid.UUID, Query()],
    date: Annotated[dt.date, Query(description="Fecha local del negocio")],
) -> AvailabilityOut:
    return await availability_service.get_availability(session, service_id, date)
