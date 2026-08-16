from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RoomCalendarCreate(BaseModel):
    room_id: int
    platform_id: int
    import_url: str | None = None


class RoomCalendarUpdate(BaseModel):
    import_url: str | None = None


class RoomCalendarResponse(BaseModel):
    id: int
    room_id: int
    platform_id: int
    import_url: str | None
    active: bool
    last_sync_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class IcalSyncResponse(BaseModel):
    room_calendar_id: int
    received: int
    created: int
    updated: int
    unchanged: int
    cancelled: int
    disappeared: int
