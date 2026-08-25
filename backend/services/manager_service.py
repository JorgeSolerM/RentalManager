import logging

from sqlalchemy.orm import Session

from backend.core.image_processing import ImageProcessingError, SafeImageProcessor
from backend.core.media_storage import MediaFileStore
from backend.core.operation_result import OperationResult
from backend.models.manager import Manager
from backend.models.media_asset import MediaAsset
from backend.repositories.manager_repository import ManagerRepository
from backend.repositories.photo_repository import PhotoRepository
from backend.services.photo_service import UploadPayload


logger = logging.getLogger(__name__)


class ManagerService:
    def __init__(self, repository=None, processor=None, store=None):
        self.repository = repository or ManagerRepository()
        self.store = store or MediaFileStore()
        self.processor = processor or SafeImageProcessor(self.store)
        self.photo_repository = PhotoRepository()

    def list_all(self, db: Session):
        return self.repository.list_all(db)

    def active_options(self, db: Session, selected_id=None):
        return self.repository.active_options(db, selected_id)

    def save(self, db: Session, manager_id: int | None, *, name: str, phone: str = "", active: bool):
        normalized = " ".join(name.split())
        if not normalized:
            return OperationResult(False, "manager_name_required")
        manager = self.repository.get(db, manager_id) if manager_id else Manager()
        if manager is None:
            return OperationResult(False, "not_found")
        try:
            manager.name = normalized
            manager.phone = " ".join(phone.split()) or None
            manager.active = active
            db.add(manager)
            db.flush()
            db.commit()
            return OperationResult(True, data=manager)
        except Exception:
            db.rollback()
            raise

    def assign_unassigned(self, db: Session, manager_id: int):
        manager = self.repository.get(db, manager_id)
        if manager is None or not manager.active:
            return OperationResult(False, "manager_invalid")
        try:
            count = self.repository.assign_unassigned(db, manager_id)
            db.flush()
            db.commit()
            return OperationResult(True, data=count)
        except Exception:
            db.rollback()
            raise

    def upload_photo(self, db: Session, manager_id: int, upload: UploadPayload):
        manager = self.repository.get(db, manager_id)
        if manager is None:
            return OperationResult(False, "not_found")
        created_key = None
        quarantine = None
        old_asset = manager.photo
        try:
            processed = self.processor.process(upload.content, upload.content_type)
            created_key = processed.storage_key
            asset = self.repository.asset_by_checksum(db, processed.checksum_sha256)
            if asset is not None:
                self.store.remove_asset(created_key)
                created_key = None
            else:
                asset = MediaAsset(
                    storage_key=processed.storage_key,
                    mime_type=processed.mime_type,
                    width=processed.width,
                    height=processed.height,
                    byte_size=processed.byte_size,
                    checksum_sha256=processed.checksum_sha256,
                    status="ready",
                )
                db.add(asset)
                db.flush()
            manager.media_asset_id = asset.id
            db.flush()
            if old_asset and old_asset.id != asset.id and self.photo_repository.asset_reference_count(db, old_asset.id) == 0:
                quarantine = self.store.quarantine_asset(old_asset.storage_key)
                db.delete(old_asset)
                db.flush()
            db.commit()
            if quarantine:
                self.store.purge_quarantine(quarantine)
            return OperationResult(True)
        except ImageProcessingError as exc:
            db.rollback()
            if created_key:
                self.store.remove_asset(created_key)
            return OperationResult(False, str(exc))
        except Exception:
            db.rollback()
            if created_key:
                self.store.remove_asset(created_key)
            if old_asset:
                self.store.restore_quarantine(old_asset.storage_key, quarantine)
            raise
