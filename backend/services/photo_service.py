from dataclasses import dataclass
import logging

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.core.image_processing import ImageProcessingError, SafeImageProcessor
from backend.core.media_storage import MediaFileStore
from backend.core.operation_result import OperationResult
from backend.models.media_asset import MediaAsset
from backend.models.property_photo import PropertyPhoto
from backend.models.room_photo import RoomPhoto
from backend.repositories.photo_repository import PhotoRepository
from backend.schemas.photo_schema import PhotoGalleryItem, RoomPhotoGallery


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadPayload:
    content: bytes
    content_type: str | None


class PhotoService:
    def __init__(
        self,
        repository: PhotoRepository | None = None,
        processor: SafeImageProcessor | None = None,
        store: MediaFileStore | None = None,
    ):
        self.repository = repository or PhotoRepository()
        self.store = store or MediaFileStore()
        self.processor = processor or SafeImageProcessor(self.store)

    @staticmethod
    def variant_url(asset_id: int, width: int = 320) -> str:
        return f"/media-assets/{asset_id}/variants/{width}"

    def property_gallery(self, db: Session, property_id: int) -> tuple[PhotoGalleryItem, ...]:
        return tuple(self._dto(photo) for photo in self.repository.list_property_photos(db, property_id))

    def room_gallery(self, db: Session, room_id: int) -> RoomPhotoGallery:
        own = tuple(self._dto(photo) for photo in self.repository.list_room_photos(db, room_id))
        fallback = None
        if not any(item.is_primary for item in own):
            room = self.repository.get_room(db, room_id)
            if room is not None:
                property_photos = self.repository.list_property_photos(db, room.property_id)
                primary = next((photo for photo in property_photos if photo.is_primary and photo.asset.status == "ready"), None)
                fallback = self._dto(primary) if primary else None
        return RoomPhotoGallery(photos=own, fallback_photo=fallback)

    def upload_property(self, db: Session, property_id: int, uploads: list[UploadPayload]) -> OperationResult:
        if self.repository.get_property(db, property_id) is None:
            return OperationResult(False, "not_found")
        return self._upload(db, "property", property_id, uploads)

    def upload_room(self, db: Session, room_id: int, uploads: list[UploadPayload]) -> OperationResult:
        if self.repository.get_room(db, room_id) is None:
            return OperationResult(False, "not_found")
        return self._upload(db, "room", room_id, uploads)

    def _upload(self, db: Session, owner_type: str, owner_id: int, uploads: list[UploadPayload]) -> OperationResult:
        if not uploads:
            return OperationResult(False, "media_file_required")
        created_keys: list[str] = []
        try:
            existing_photos = self._list(db, owner_type, owner_id)
            existing_asset_ids = {photo.media_asset_id for photo in existing_photos}
            position = len(existing_photos)
            for upload in uploads:
                processed = self.processor.process(upload.content, upload.content_type)
                created_keys.append(processed.storage_key)
                asset = self.repository.get_asset_by_checksum(db, processed.checksum_sha256)
                if asset is not None:
                    self.store.remove_asset(processed.storage_key)
                    created_keys.remove(processed.storage_key)
                else:
                    asset = MediaAsset(
                        storage_key=processed.storage_key,
                        mime_type=processed.mime_type,
                        width=processed.width,
                        height=processed.height,
                        byte_size=processed.byte_size,
                        checksum_sha256=processed.checksum_sha256,
                        status="processing",
                    )
                    self.repository.add(db, asset)
                if asset.id in existing_asset_ids:
                    raise ImageProcessingError("media_duplicate_photo")
                photo_class = PropertyPhoto if owner_type == "property" else RoomPhoto
                owner_field = {"property_id": owner_id} if owner_type == "property" else {"room_id": owner_id}
                self.repository.add(db, photo_class(
                    **owner_field,
                    media_asset_id=asset.id,
                    position=position,
                    is_primary=(position == 0),
                ))
                asset.status = "ready"
                existing_asset_ids.add(asset.id)
                position += 1
            db.commit()
            return OperationResult(True)
        except ImageProcessingError as exc:
            db.rollback()
            for key in created_keys:
                self.store.remove_asset(key)
            return OperationResult(False, str(exc))
        except Exception:
            db.rollback()
            for key in created_keys:
                self.store.remove_asset(key)
            raise

    def set_primary(self, db: Session, owner_type: str, photo_id: int) -> OperationResult:
        photo = self._get_photo(db, owner_type, photo_id)
        if photo is None:
            return OperationResult(False, "not_found")
        if photo.is_primary:
            return OperationResult(True)
        try:
            photo_class = PropertyPhoto if owner_type == "property" else RoomPhoto
            owner_column = (
                PropertyPhoto.property_id if owner_type == "property" else RoomPhoto.room_id
            )
            db.execute(
                update(photo_class)
                .where(
                    owner_column == self._owner_id(owner_type, photo),
                    photo_class.is_primary.is_(True),
                )
                .values(is_primary=False)
            )
            # The separate flush is intentional: the partial unique index must
            # observe zero principals before the selected photo becomes primary.
            db.flush()
            photo.is_primary = True
            db.flush()
            db.commit()
            return OperationResult(True)
        except Exception:
            db.rollback()
            raise

    def reorder(self, db: Session, owner_type: str, photo_id: int, direction: str) -> OperationResult:
        photo = self._get_photo(db, owner_type, photo_id)
        if photo is None:
            return OperationResult(False, "not_found")
        if direction not in {"up", "down"}:
            return OperationResult(False, "media_invalid_direction")
        try:
            photos = self._list(db, owner_type, self._owner_id(owner_type, photo))
            index = next(index for index, item in enumerate(photos) if item.id == photo.id)
            target = index - 1 if direction == "up" else index + 1
            if target < 0 or target >= len(photos):
                return OperationResult(True)
            # Temporary high positions avoid the unique owner/position index while
            # preserving the non-negative schema invariant.
            for order, item in enumerate(photos):
                item.position = 1_000_000 + order
            db.flush()
            photos[index], photos[target] = photos[target], photos[index]
            for order, item in enumerate(photos):
                item.position = order
            db.flush()
            db.commit()
            return OperationResult(True)
        except Exception:
            db.rollback()
            raise

    def reorder_exact(
        self,
        db: Session,
        owner_type: str,
        owner_id: int,
        photo_ids: list[int],
    ) -> OperationResult:
        if owner_type not in {"property", "room"}:
            return OperationResult(False, "not_found")
        photos = self._list(db, owner_type, owner_id)
        existing_ids = [photo.id for photo in photos]
        if len(photo_ids) != len(set(photo_ids)) or set(photo_ids) != set(existing_ids):
            return OperationResult(False, "media_invalid_order")
        if photo_ids == existing_ids:
            return OperationResult(True)
        by_id = {photo.id: photo for photo in photos}
        try:
            for temporary_position, photo in enumerate(photos, start=1_000_000):
                photo.position = temporary_position
            db.flush()
            for position, photo_id in enumerate(photo_ids):
                by_id[photo_id].position = position
            db.flush()
            db.commit()
            return OperationResult(True)
        except Exception:
            db.rollback()
            raise

    def delete_photo(self, db: Session, owner_type: str, photo_id: int) -> OperationResult:
        photo = self._get_photo(db, owner_type, photo_id)
        if photo is None:
            return OperationResult(False, "not_found")
        asset = photo.asset
        quarantine = None
        try:
            owner_id = self._owner_id(owner_type, photo)
            self.repository.delete(db, photo)
            photos = self._list(db, owner_type, owner_id)
            for order, item in enumerate(photos):
                item.position = 1_000_000 + order
            db.flush()
            for order, item in enumerate(photos):
                item.position = order
                item.is_primary = order == 0 if photo.is_primary else item.is_primary
            db.flush()
            if self.repository.asset_reference_count(db, asset.id) == 0:
                quarantine = self.store.quarantine_asset(asset.storage_key)
                self.repository.delete(db, asset)
            db.commit()
            try:
                self.store.purge_quarantine(quarantine)
            except OSError:
                logger.exception("Could not purge quarantined media asset %s", asset.id)
            return OperationResult(True)
        except Exception:
            db.rollback()
            self.store.restore_quarantine(asset.storage_key, quarantine)
            raise

    def variant_path(self, db: Session, asset_id: int, width: int):
        asset = self.repository.get_asset(db, asset_id)
        if asset is None or asset.status != "ready":
            return None
        try:
            path = self.store.asset_file(asset.storage_key, width)
        except ValueError:
            return None
        return path if path.is_file() else None

    def _list(self, db, owner_type, owner_id):
        return self.repository.list_property_photos(db, owner_id) if owner_type == "property" else self.repository.list_room_photos(db, owner_id)

    def _get_photo(self, db, owner_type, photo_id):
        return self.repository.get_property_photo(db, photo_id) if owner_type == "property" else self.repository.get_room_photo(db, photo_id)

    @staticmethod
    def _owner_id(owner_type, photo):
        return photo.property_id if owner_type == "property" else photo.room_id

    def _dto(self, photo) -> PhotoGalleryItem:
        return PhotoGalleryItem(
            id=photo.id,
            asset_id=photo.asset.id,
            position=photo.position,
            is_primary=photo.is_primary,
            thumbnail_url=self.variant_url(photo.asset.id),
            width=photo.asset.width,
            height=photo.asset.height,
        )
