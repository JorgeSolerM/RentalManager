from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from backend.database.base import Base
import backend.database.session as database_session
import backend.models  # noqa: F401


@pytest.mark.alembic_audit
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known migration debt: the initial revision does not create the "
        "properties and rooms tables required by the complete ORM schema."
    ),
)
def test_alembic_upgrade_head_builds_complete_schema_in_temporary_sqlite(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "alembic_audit.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(database_session, "DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        assert set(Base.metadata.tables).issubset(
            inspect(engine).get_table_names()
        )
    finally:
        engine.dispose()
