import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_reconciliation_audit_migration(tmp_path,monkeypatch):
    path=tmp_path/'reconciliation.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE','1')
    cfg=Config('alembic.ini');command.upgrade(cfg,'bac2e4f6d893')
    for action,rev in [(command.upgrade,'cbd3e5f7a904'),(command.downgrade,'bac2e4f6d893'),(command.upgrade,'cbd3e5f7a904')]:
        action(cfg,rev)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('pragma quick_check').fetchone()==('ok',)
            assert db.execute('pragma foreign_key_check').fetchall()==[]
            if rev=='cbd3e5f7a904':assert db.execute('select count(*) from migration_runs').fetchone()==(0,)
    with closing(sqlite3.connect(path)) as db:
        db.execute("insert into migration_runs(id,source,source_digest,plan_digest,result) values ('test','NetFincas','test','test','applied')");db.commit()
    with pytest.raises(RuntimeError,match='trazabilidad'):command.downgrade(cfg,'bac2e4f6d893')
