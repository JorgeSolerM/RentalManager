from sqlalchemy.orm import Session

from backend.models.platform import Platform
from backend.repositories.platform_repository import PlatformRepository


class PlatformService:

    def __init__(self):

        self.platform_repository = PlatformRepository()

    def list_platforms(
        self,
        db: Session,
    ) -> list[Platform]:

        return self.platform_repository.get_all(
            db,
        )

    def create_platform(
        self,
        db: Session,
        platform: Platform,
    ) -> Platform:

        return self.platform_repository.create(
            db,
            platform,
        )
