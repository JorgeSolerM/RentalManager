from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database.session import DATABASE_PATH


PUBLIC_DATABASE_URL = (
    f"sqlite:///file:{DATABASE_PATH.as_posix()}?mode=ro&uri=true"
)

public_engine = create_engine(
    PUBLIC_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
PublicSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=public_engine,
)


def get_public_db() -> Generator[Session, None, None]:
    session = PublicSessionLocal()
    try:
        yield session
    finally:
        session.close()
