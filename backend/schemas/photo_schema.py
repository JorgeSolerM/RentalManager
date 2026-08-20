from dataclasses import dataclass
from pydantic import BaseModel


@dataclass(frozen=True)
class PhotoGalleryItem:
    id: int
    asset_id: int
    position: int
    is_primary: bool
    thumbnail_url: str
    width: int
    height: int


@dataclass(frozen=True)
class RoomPhotoGallery:
    photos: tuple[PhotoGalleryItem, ...]
    fallback_photo: PhotoGalleryItem | None


class PhotoOrderRequest(BaseModel):
    owner_id: int
    photo_ids: list[int]
