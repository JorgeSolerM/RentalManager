from datetime import date

from backend.schemas.publication_schema import (
    FeatureCatalogItem,
    PublicAvailability,
    RoomPublicationAssessment,
    EffectivePhoto,
)
from backend.schemas.photo_schema import PhotoGalleryItem, RoomPhotoGallery

__all__ = [
    "FeatureCatalogItem",
    "PublicAvailability",
    "RoomPublicationAssessment",
    "EffectivePhoto",
    "PhotoGalleryItem",
    "RoomPhotoGallery",
]

from pydantic import BaseModel, ConfigDict


class BookingResponse(BaseModel):

    id: int

    room_id: int

    guest_name: str | None

    origin: str

    check_in: date

    check_out: date

    price: float | None

    notes: str | None

    editable: bool

    model_config = ConfigDict(
        from_attributes=True,
    )


class BookingCreate(BaseModel):
    pass


class BookingUpdate(BaseModel):
    pass
