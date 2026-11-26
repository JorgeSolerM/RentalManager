"""New economic routes retain existing CSRF and remote capabilities."""
import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from backend.app_factory import create_app
from backend.database.session import get_db
from backend.core.admin_security import AdminSecurityMiddleware
from backend.models.owner_loss_compensation import OwnerLossCompensationAuthorization as Authorization, OwnerLossCompensationApplication as Application
from tests.unit.test_owner_loss_compensations import sample, paid, setup, application_values
from tests.integration.test_admin_remote_security import config, key, verifier, headers

@pytest.fixture
def secured_app(db_session, config, key):
    app = create_app(False)
    app.dependency_overrides[get_db] = lambda: db_session
    for middleware in app.user_middleware:
        if middleware.cls is AdminSecurityMiddleware:
            middleware.kwargs.update(config=config, verifier=verifier(config, key))
    return app

@pytest.mark.parametrize('action', ['preview', 'confirm'])
def test_csrf_rejection_is_navigable_and_does_not_write(secured_app, db_session, paid, action):
    s, p, bank = paid
    i, loss, auth = setup(db_session, s, p)
    url = f'/transfer-incidents/{i.id}/compensations'
    with TestClient(secured_app, base_url='http://127.0.0.1', client=('127.0.0.1', 111)) as client:
        assert client.get(url).status_code == 200
        for token in ('', 'invalid'):
            response = client.post(url + '/' + action, data=application_values(s, auth) | {'_rm_csrf': token}, headers={'Accept': 'text/html'})
            assert response.status_code == 403
            assert 'Volver al formulario' in response.text and 'Ir al inicio' in response.text
    assert db_session.scalar(select(func.count()).select_from(Application)) == 0
    assert db_session.scalar(select(func.count()).select_from(Authorization)) == 1

def test_remote_settlement_hides_links_and_rejects_new_routes(secured_app, db_session, paid, key):
    s, p, bank = paid
    i, loss, auth = setup(db_session, s, p)
    with TestClient(secured_app, base_url='https://admin.example.test', client=('127.0.0.1', 111), headers=headers(key)) as client:
        response = client.get(f'/settlements/{s.id}')
        assert response.status_code == 200
        assert 'Modo consulta' in response.text
        assert 'Resultado económico y fondos' not in response.text  # Preserve current remote exposure.
        assert '/compensations' not in response.text
        token = re.search('name="rm-admin-csrf" content="([^"]+)"', response.text)[1]
        for url in (f'/settlements/{s.id}/compensations', f'/transfer-incidents/{i.id}/compensations'):
            assert client.get(url).status_code == 403
        for action in ('preview', 'confirm'):
            response = client.post(f'/transfer-incidents/{i.id}/compensations/{action}', data=application_values(s, auth), headers={'X-RM-CSRF': token})
            assert response.status_code == 403 and response.json()['code'] == 'read_only_denied'
    assert db_session.scalar(select(func.count()).select_from(Application)) == 0
