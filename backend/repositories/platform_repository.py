from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.platform import Platform

from backend.repositories.base_repository import BaseRepository


class PlatformRepository(BaseRepository):

    def get_all(
        self,
        db: Session,
    ) -> list[Platform]:

        statement = (
            select(Platform)
            .order_by(Platform.name)
        )

        return db.scalars(statement).all()
