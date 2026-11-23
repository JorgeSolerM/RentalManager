"""Read-only SQLite connection for remote administration, reset before pool reuse."""
from fastapi import Request
from sqlalchemy.orm import Session
from backend.database.session import get_db, engine


def admin_get_db(request: Request):
    remote = getattr(request.state, 'admin_remote', False)
    if not remote:
        yield from get_db()
        return
    with engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA query_only=ON')
        try:
            with Session(bind=connection) as db:
                yield db
        finally:
            try:
                connection.rollback()
                connection.exec_driver_sql('PRAGMA query_only=OFF')
                connection.rollback()
            except Exception:
                connection.invalidate()
                raise
