from sqlalchemy.orm import Session


class BaseRepository:

    def create(
        self,
        db: Session,
        entity,
    ):

        db.add(entity)

        db.commit()

        db.refresh(entity)

        return entity

    def update(
        self,
        db: Session,
        entity,
    ):

        db.commit()

        db.refresh(entity)

        return entity
