import datetime as dt
import uuid

from pydantic import BaseModel


class SlotOut(BaseModel):
    start_at: dt.datetime
    local_time: dt.time


class AvailabilityOut(BaseModel):
    service_id: uuid.UUID
    date: dt.date
    timezone: str
    duration_minutes: int
    buffer_minutes: int
    slots: list[SlotOut]
