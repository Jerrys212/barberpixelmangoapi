import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from src.auth.dependencies import ClientInfoDep, OwnerUser
from src.database import SessionDep
from src.schedule import service as schedule_service
from src.schedule.models import ScheduleException, WeeklyInterval
from src.schedule.schemas import (
    ExceptionCreate,
    ExceptionOut,
    WeeklyIntervalOut,
    WeeklyScheduleIn,
)

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/weekly", response_model=list[WeeklyIntervalOut])
async def read_weekly(session: SessionDep) -> Sequence[WeeklyInterval]:
    return await schedule_service.get_weekly(session)


@router.put("/weekly", response_model=list[WeeklyIntervalOut])
async def replace_weekly(
    data: WeeklyScheduleIn, owner: OwnerUser, session: SessionDep, client: ClientInfoDep
) -> Sequence[WeeklyInterval]:
    return await schedule_service.replace_weekly(session, owner, data, client)


@router.get("/exceptions", response_model=list[ExceptionOut])
async def list_exceptions(
    _: OwnerUser,
    session: SessionDep,
    date_from: Annotated[dt.date, Query()],
    date_to: Annotated[dt.date, Query()],
) -> Sequence[ScheduleException]:
    return await schedule_service.list_exceptions(session, date_from, date_to)


@router.post("/exceptions", response_model=list[ExceptionOut], status_code=status.HTTP_201_CREATED)
async def create_exceptions(
    data: Annotated[ExceptionCreate, Body()],
    owner: OwnerUser,
    session: SessionDep,
    client: ClientInfoDep,
) -> list[ScheduleException]:
    return await schedule_service.create_exceptions(session, owner, data, client)


@router.delete("/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exception(
    exception_id: uuid.UUID, owner: OwnerUser, session: SessionDep, client: ClientInfoDep
) -> None:
    await schedule_service.delete_exception(session, owner, exception_id, client)
