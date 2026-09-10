"""Shared write boundary for manual receipts and bank instructions (SQLite)."""
from contextlib import contextmanager
from sqlalchemy import text


@contextmanager
def financial_transaction(db):
    if db.new or db.dirty or db.deleted:
        raise ValueError('La operación requiere una sesión sin cambios pendientes.')
    # Discard only the read transaction, then lock before checking any balances.
    db.rollback()
    try:
        db.execute(text('BEGIN IMMEDIATE'))
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise
