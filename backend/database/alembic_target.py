import os
from pathlib import Path

from sqlalchemy.engine import make_url

from backend.database.session import DATABASE_PATH, DATABASE_URL


DATABASE_URL_OVERRIDE_ENV = "DATABASE_URL"
REQUIRE_TEMPORARY_ENV = "ALEMBIC_REQUIRE_TEMPORARY_DATABASE"


def resolve_alembic_database_url() -> str:
    return os.environ.get(DATABASE_URL_OVERRIDE_ENV) or DATABASE_URL


def sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database).resolve()


def validate_alembic_target(database_url: str) -> Path | None:
    resolved_path = sqlite_database_path(database_url)
    require_temporary = os.environ.get(REQUIRE_TEMPORARY_ENV, "").strip().lower()
    if require_temporary in {"1", "true", "yes"}:
        if resolved_path is None:
            raise RuntimeError(
                "Temporary Alembic validation requires a file-backed SQLite database."
            )
        if resolved_path == DATABASE_PATH.resolve():
            raise RuntimeError(
                "Alembic temporary-database guard refused data/RentalManager.db."
            )
    return resolved_path
