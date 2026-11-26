"""Opt-in installed Playwright/Edge; no new project dependency."""
import os
import subprocess
from pathlib import Path
import pytest
from sqlalchemy import select, func
from backend.models.owner_loss_compensation import OwnerLossCompensationApplication as Application
from tests.unit.test_owner_loss_compensations import sample, paid, register, owner_loss, balances
from tests.integration.api.test_payment_correction_http import live_http

@pytest.mark.skipif(not os.environ.get('RM_RUN_BROWSER'), reason='Requires installed Playwright and Edge')
def test_native_forms_mobile_and_desktop(live_http, db_session, paid, tmp_path):
    s, p, bank = paid
    i = register(db_session, s, p)
    loss = owner_loss(db_session, s, i)
    out = Path(os.environ.get('RM_BROWSER_OUTPUT', str(tmp_path / 'browser')))
    result = subprocess.run(['node', 'tests/frontend/owner_loss_compensations.cjs', str(live_http.base_url).rstrip('/'), str(i.id), str(loss.id), str(s.id), str(out)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(Application)) == 1
    assert balances.summary(db_session, s)['compensated'] == 40
