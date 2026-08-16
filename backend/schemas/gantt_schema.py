from datetime import date

from pydantic import BaseModel


class GanttWindow(BaseModel):
    start: date
    end: date
    today: date
    day_count: int


class GanttOrigin(BaseModel):
    slug: str
    name: str
    favicon: str | None = None
    color_key: str


class GanttBooking(BaseModel):
    id: int
    check_in: date
    check_out: date
    guest_name: str
    origin: GanttOrigin
    editable: bool
    historical: bool
    overlap_kind: str | None = None
    lane: int = 0


class GanttSyncPlatform(BaseModel):
    slug: str
    name: str
    state: str


class GanttSyncState(BaseModel):
    severity: str
    platforms: list[GanttSyncPlatform]


class GanttRoom(BaseModel):
    id: int
    code: str
    active: bool
    sync: GanttSyncState
    bookings: list[GanttBooking]


class GanttProperty(BaseModel):
    id: int
    name: str
    rooms: list[GanttRoom]


class GanttData(BaseModel):
    schema_version: int = 1
    window: GanttWindow
    properties: list[GanttProperty]

