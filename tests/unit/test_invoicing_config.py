from types import SimpleNamespace
import pytest

from backend.core.invoicing_config import invoicing_config, require_synthetic_invoicing


def test_flags_disabled_by_default(monkeypatch):
    for key in ('INVOICING_ENABLED', 'VERIFACTU_ENABLED', 'VERIFACTU_SUBMISSION_ENABLED'):
        monkeypatch.delenv(key, raising=False)
    assert not any(vars(invoicing_config()).values())


def test_submission_cannot_be_enabled_accidentally(monkeypatch):
    monkeypatch.setenv('INVOICING_ENABLED', 'true')
    monkeypatch.setenv('VERIFACTU_SUBMISSION_ENABLED', 'true')
    with pytest.raises(ValueError, match='deshabilitados'):
        invoicing_config()


def test_explicit_synthetic_path_required(db_session, monkeypatch):
    monkeypatch.setenv('INVOICING_ENABLED', 'true')
    monkeypatch.delenv('VERIFACTU_SUBMISSION_ENABLED', raising=False)
    monkeypatch.delenv('INVOICING_SYNTHETIC_DATABASE', raising=False)
    with pytest.raises(ValueError, match='sintética'):
        require_synthetic_invoicing(db_session)
    monkeypatch.setenv('INVOICING_SYNTHETIC_DATABASE', db_session.get_bind().url.database)
    assert require_synthetic_invoicing(db_session).enabled


def test_production_path_rejected_without_opening_db(monkeypatch):
    from pathlib import Path
    production = str(Path(__file__).resolve().parents[2] / 'data' / 'RentalManager.db')
    monkeypatch.setenv('INVOICING_ENABLED', 'true')
    monkeypatch.setenv('VERIFACTU_SUBMISSION_ENABLED', 'false')
    monkeypatch.setenv('INVOICING_SYNTHETIC_DATABASE', production)
    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(url=SimpleNamespace(database=production)))
    with pytest.raises(ValueError, match='BD real'):
        require_synthetic_invoicing(db)
