from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.platform import Platform
from backend.repositories.platform_repository import PlatformRepository
from backend.repositories.room_calendar_repository import RoomCalendarRepository


class PlatformService:

    def __init__(self):

        self.repository = PlatformRepository()
        self.room_calendar_repository = RoomCalendarRepository()

    def list_platforms(
        self,
        db: Session,
    ) -> list[Platform]:

        return self.repository.get_all(db)

    def create_platform(
        self,
        db: Session,
        platform: Platform,
    ) -> OperationResult[Platform]:

        existing = self.repository.get_by_slug(
            db,
            platform.slug,
        )

        if existing is not None:

            return OperationResult(
                success=False,
                message="slug_exists",
            )

        try:
            self.repository.create(db, platform)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return OperationResult(
            success=True,
            data=platform,
        )

    def update_platform(
        self,
        db: Session,
        platform_id: int,
        name: str,
        slug: str,
        supports_import: bool,
        supports_export: bool,
    ) -> OperationResult[Platform]:

        platform = self.get_by_id(
            db,
            platform_id,
        )

        if platform is None:

            return OperationResult(
                success=False,
                message="not_found",
            )

        existing = self.get_by_slug(
            db,
            slug,
        )

        if (
            existing is not None
            and existing.id != platform.id
        ):

            return OperationResult(
                success=False,
                message="slug_exists",
            )

        if self.room_calendar_repository.has_incompatible_urls(
            db,
            platform.id,
            supports_import,
            supports_export,
        ):
            return OperationResult(
                success=False,
                message="platform_capabilities_in_use",
            )

        try:
            platform.name = name
            platform.slug = slug
            platform.supports_import = supports_import
            platform.supports_export = supports_export
            self.repository.update(db, platform)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return OperationResult(
            success=True,
            data=platform,
        )

    def delete_platform(
        self,
        db: Session,
        platform_id: int,
    ) -> OperationResult[None]:

        platform = self.get_by_id(
            db,
            platform_id,
        )

        if platform is None:

            return OperationResult(
                success=False,
                message="not_found",
            )

        if self.repository.has_room_calendars(db, platform.id):

            return OperationResult(
                success=False,
                message="platform_has_room_calendars",
            )

        try:
            self.repository.delete(db, platform)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return OperationResult(
            success=True,
        )

    def get_by_id(
        self,
        db: Session,
        platform_id: int,
    ) -> Platform | None:

        return self.repository.get_by_id(
            db,
            platform_id,
        )

    def get_by_slug(
        self,
        db: Session,
        slug: str,
    ) -> Platform | None:

        return self.repository.get_by_slug(
            db,
            slug,
        )
