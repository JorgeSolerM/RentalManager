import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_category_metadata_upgrade_downgrade_reupgrade(tmp_path, monkeypatch):
    path = tmp_path / 'categories.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE', '1')
    cfg = Config('alembic.ini')
    command.upgrade(cfg, 'edf507b9c126')
    with closing(sqlite3.connect(path)) as db:
        before = db.execute('select id,code,name,active from expense_categories order by id').fetchall()
        db.execute("insert into providers(legal_name,default_expense_category_id) values ('Proveedor ficticio',1)")
        db.commit()
    for operation, revision in ((command.upgrade,'fe0618cad237'), (command.downgrade,'edf507b9c126'), (command.upgrade,'fe0618cad237')):
        operation(cfg, revision)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('pragma quick_check').fetchone() == ('ok',)
            assert db.execute('pragma foreign_key_check').fetchall() == []
            assert db.execute('select id,code,name,active from expense_categories order by id').fetchall() == before
            assert db.execute('select default_expense_category_id from providers').fetchone() == (1,)
            if revision == 'fe0618cad237':
                assert db.execute('select count(*) from expense_categories where created_at is not null and updated_at is not null').fetchone() == (8,)
    with closing(sqlite3.connect(path)) as db:
        db.execute("update expense_categories set description='Conservar metadatos' where id=1"); db.commit()
    with pytest.raises(RuntimeError, match='bloqueado'):
        command.downgrade(cfg, 'edf507b9c126')
