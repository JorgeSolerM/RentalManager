from datetime import date

from pydantic import BaseModel
from typing import Literal


class RoomPublicationAssessment(BaseModel):
    room_id: int
    is_publicable: bool
    reasons: list[str]
    primary_photo_source: str | None = None


class FeatureCatalogItem(BaseModel):
    id: int
    slug: str
    name: str
    scope: str
    category: str
    icon_key: str | None
    display_order: int


class PublicAvailability(BaseModel):
    status: str
    available_from: date | None = None


class EffectivePhoto(BaseModel):
    asset_id: int
    source: Literal["room", "property"]
    position: int
    is_primary: bool
    width: int
    height: int
