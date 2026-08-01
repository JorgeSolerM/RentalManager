from backend.database.base import Base
from backend.database.session import engine


def init_db():

    Base.metadata.create_all(bind=engine)
