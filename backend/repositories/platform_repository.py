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

    def get_by_id(
        self,
        db: Session,
        platform_id: int,
    ) -> Platform | None:

        statement = (
            select(Platform)
            .where(
                Platform.id == platform_id
            )
        )

        return db.scalar(statement)

    def get_by_slug(
        self,
        db: Session,
        slug: str,
    ) -> Platform | None:

        statement = (
            select(Platform)
            .where(
                Platform.slug == slug
            )
        )

        return db.scalar(statement)

    def update(
        self,
        db: Session,
        platform: Platform,
    ) -> Platform:

        db.merge(platform)

        return platform

    def delete(
        self,
        db: Session,
        platform: Platform,
    ) -> None:

        db.delete(platform)
