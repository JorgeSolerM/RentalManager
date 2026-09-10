import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database.base import Base
from backend.database.session import get_db
from backend.app_factory import create_app
import backend.models  # noqa: F401


@pytest.fixture
def db_session(tmp_path) -> Session:
    database_path = tmp_path / "rental_manager_test.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        try:
            # RESTRICT self-references (SEPA retry_of_id) prevent SQLite's
            # implicit DELETE during DROP TABLE. Disable FKs only for teardown,
            # after checking integrity, on this exact disposable pytest DB.
            assert Path(engine.url.database).resolve() == database_path.resolve()
            assert database_path.resolve().is_relative_to(tmp_path.resolve())
            with engine.connect() as connection:
                assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall() == []
                connection.commit()
                connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
                try:
                    Base.metadata.drop_all(bind=connection)
                    connection.commit()
                finally:
                    connection.exec_driver_sql('PRAGMA foreign_keys=ON')
                    connection.commit()
        finally:
            engine.dispose()


@pytest.fixture
def client(db_session: Session):
    app = create_app(initialize_database=False)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
