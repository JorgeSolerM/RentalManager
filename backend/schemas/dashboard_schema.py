from datetime import date, datetime

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    active_rooms: int
    occupied_rooms: int
    free_rooms: int
    occupancy_percentage: float
    arrivals_today: int
    departures_today: int


class DashboardMovement(BaseModel):
    booking_id: int
    room_id: int
    room_code: str
    room_display_order: int
    property_name: str
    date: date
    days_remaining: int
    guest_name: str
    origin_name: str
    origin_slug: str
    favicon: str | None = None
    imported: bool


class DashboardIncident(BaseModel):
    key: str
    kind: str
    severity: str
    title: str
    detail: str
    room_id: int
    room_code: str
    platform_name: str | None = None
    booking_id: int | None = None
    target_url: str | None = None


class DashboardAvailability(BaseModel):
    room_id: int
    room_code: str
    property_name: str
    available_from: date
    available_until: date | None = None


class DashboardPlatformSummary(BaseModel):
    slug: str
    name: str
    favicon: str | None = None
    correct: int
    review: int


class DashboardData(BaseModel):
    schema_version: int = 1
    today: date
    summary: DashboardSummary
    upcoming_arrivals: list[DashboardMovement]
    upcoming_departures: list[DashboardMovement]
    incidents: list[DashboardIncident]
    upcoming_availability: list[DashboardAvailability]
    platforms: list[DashboardPlatformSummary]
    reliable_last_update: datetime | None = None
