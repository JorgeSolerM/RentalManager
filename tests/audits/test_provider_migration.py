import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_provider_upgrade_downgrade_reupgrade(tmp_path,monkeypatch):
    path=tmp_path/'providers.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE','1')
    cfg=Config('alembic.ini')
    command.upgrade(cfg,'dce4f6a8b015')
    for operation,revision in ((command.upgrade,'edf507b9c126'),(command.downgrade,'dce4f6a8b015'),(command.upgrade,'edf507b9c126')):
        operation(cfg,revision)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('pragma quick_check').fetchone()==('ok',)
            assert db.execute('pragma foreign_key_check').fetchall()==[]
            if revision=='edf507b9c126':
                assert db.execute('select count(*) from providers').fetchone()==(0,)
                assert 'provider_id' in [r[1] for r in db.execute('pragma table_info(expenses)')]
                assert any(r[2]=='providers' and r[3]=='provider_id' for r in db.execute('pragma foreign_key_list(expenses)'))
    with closing(sqlite3.connect(path)) as db:
        db.execute("insert into providers(legal_name) values ('Proveedor sintético')");db.commit()
    with pytest.raises(RuntimeError,match='bloqueado'):
        command.downgrade(cfg,'dce4f6a8b015')
