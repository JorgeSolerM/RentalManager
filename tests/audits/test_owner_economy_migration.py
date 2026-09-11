import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_owner_economy_upgrade_downgrade_reupgrade(tmp_path, monkeypatch):
    path = tmp_path / 'owner_economy.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE', '1')
    cfg = Config('alembic.ini')
    command.upgrade(cfg, 'cbd3e5f7a904')
    for action, rev in ((command.upgrade,'dce4f6a8b015'),(command.downgrade,'cbd3e5f7a904'),(command.upgrade,'dce4f6a8b015')):
        action(cfg, rev)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('pragma quick_check').fetchone() == ('ok',)
            assert db.execute('pragma foreign_key_check').fetchall() == []
            if rev == 'dce4f6a8b015':
                for table in ('expenses','expense_payments','management_fee_terms','owner_settlements','owner_payouts'):
                    assert db.execute('select count(*) from ' + table).fetchone() == (0,)
                assert db.execute('select count(*) from expense_categories').fetchone() == (8,)
    from scripts.seed_owner_economy_demo import seed
    command.upgrade(cfg, 'head')  # Runtime Expense model includes optional Provider.
    seed(path)
    with closing(sqlite3.connect(path)) as db:
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            db.execute("update owner_settlements set status='draft' where status='closed'")
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            db.execute('update owner_settlement_lines set amount=0')
        db.rollback()
        assert db.execute('pragma foreign_key_check').fetchall() == []
    with pytest.raises(RuntimeError, match='actividad económica'):
        command.downgrade(cfg, 'cbd3e5f7a904')
