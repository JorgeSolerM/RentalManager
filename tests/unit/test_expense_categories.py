from datetime import date
from sqlalchemy import select, func
import pytest

from backend.models.property import Property
from backend.models.owner_settlement import ExpenseCategory, Expense, ExpensePayment
from backend.services.expense_category_service import ExpenseCategoryService
from backend.services.expense_service import ExpenseService
from backend.services.provider_service import ProviderService

service = ExpenseCategoryService()


def test_shared_directory_tabs_and_crud(client, db_session):
    html = client.get('/providers').text
    assert 'Configuración de proveedores' in html and '+ Nuevo proveedor' in html
    assert '+ Nueva categoría' not in html
    html = client.get('/providers/categories').text
    assert '+ Nueva categoría' in html and '+ Nuevo proveedor' not in html
    assert 'href="/expenses"' in html
    response = client.post('/providers/categories/new', data={'name': '  Reparación   local ', 'description': 'Descripción', 'sort_order': '2', 'active': '1'}, follow_redirects=False)
    assert response.status_code == 303
    item = db_session.scalar(select(ExpenseCategory))
    assert item.name == 'Reparación local' and item.description == 'Descripción' and item.sort_order == 2
    assert item.created_at and item.updated_at
    original_code = item.code
    assert client.get(f'/providers/categories/{item.id}/edit').status_code == 200
    response = client.post(f'/providers/categories/{item.id}/edit', data={'name': 'Mantenimiento especial', 'active': '1'}, follow_redirects=False)
    assert response.status_code == 303
    db_session.refresh(item)
    assert item.name == 'Mantenimiento especial' and item.code == original_code
    assert item.description is None and item.sort_order is None
    for flag in ('0', '1'):
        assert client.post(f'/providers/categories/{item.id}/active', data={'active': flag}, follow_redirects=False).status_code == 303
        db_session.refresh(item)
        assert item.active == (flag == '1')
    assert client.post(f'/providers/categories/{item.id}/delete').status_code in (404, 405)
    assert client.get('/providers/categories/999/edit').status_code == 404


@pytest.mark.parametrize('values', [dict(name=''), dict(name='x'*121), dict(name='Nueva', description='x'*2001), dict(name='Nueva', sort_order='abc'), dict(name='Nueva', sort_order='-1'), dict(name='Nueva', sort_order='1000000')])
def test_invalid_category_rejected(db_session, values):
    with pytest.raises(ValueError):
        service.save(db_session, **values)
    assert db_session.scalar(select(func.count()).select_from(ExpenseCategory)) == 0


def test_duplicate_and_order(db_session, client):
    first = service.save(db_session, name='Reparación', active=False)
    assert 'Ya existe' in client.post('/providers/categories/new', data={'name': ' reparacion ', 'active': '1'}).text
    second = service.save(db_session, name='Zeta', sort_order=1)
    third = service.save(db_session, name='Alfa', sort_order=0)
    assert [c.id for c in service.list(db_session)] == [third.id, second.id, first.id]
    assert [c.id for c in service.list(db_session, active_only=True)] == [third.id, second.id]


def test_inactive_preserves_history_and_blocks_new_assignments(db_session, client):
    cat = service.save(db_session, name='Categoría histórica')
    other = service.save(db_session, name='Otra categoría')
    provider = ProviderService().save(db_session, legal_name='Proveedor ficticio', default_expense_category_id=cat.id)
    prop = Property(name='Finca sintética', address='Calle Ejemplo', city='Elche', owner='')
    db_session.add(prop); db_session.commit()
    params = dict(property_id=prop.id, category_id=cat.id, expense_date=date(2026,9,1), concept='Prueba', base_amount='100', vat_rate='0', withholding_rate='0')
    historical = ExpenseService().create(db_session, **params, provider_id=provider.id)
    service.set_active(db_session, cat.id, False)
    assert 'Categoría histórica · Inactiva' in client.get(f'/expenses/{historical.id}').text
    for url in ('/providers', f'/providers/{provider.id}', f'/providers/{provider.id}/edit'):
        assert 'Categoría histórica · Inactiva' in client.get(url).text
    assert 'Categoría histórica' not in client.get('/providers/new').text
    assert 'Categoría histórica' not in client.get('/expenses/new').text
    # Error paths must not reintroduce inactive selections either.
    assert 'Categoría histórica' not in client.post('/expenses/new', data={'category_id': cat.id}).text
    assert 'Categoría histórica' not in client.post('/providers/new', data={'legal_name': 'Otro', 'default_expense_category_id': cat.id}).text
    with pytest.raises(ValueError, match='no disponible'):
        ExpenseService().create(db_session, **params)
    with pytest.raises(ValueError, match='no disponible'):
        ProviderService().save(db_session, legal_name='Nuevo', default_expense_category_id=cat.id)
    ProviderService().save(db_session, provider.id, legal_name='Renombrado', default_expense_category_id=cat.id)
    # An explicit expense override never changes the provider default.
    params['category_id'] = other.id
    ExpenseService().create(db_session, **params, provider_id=provider.id)
    ExpenseService().create(db_session, **params)
    db_session.refresh(provider)
    assert provider.default_expense_category_id == cat.id
    assert db_session.scalar(select(func.count()).select_from(Expense)) == 3
    assert db_session.scalar(select(func.count()).select_from(ExpensePayment)) == 0
    assert client.get('/expenses').status_code == 200


def test_category_routes_are_private():
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as public:
        for url in ('/providers/categories', '/providers/categories/new', '/providers/categories/1/edit'):
            assert public.get(url).status_code == 404
            assert public.post(url, data={'name': 'Inaccesible'}).status_code in (404,405)


def test_provider_default_label_optional_and_help(client, db_session):
    provider = ProviderService().save(db_session, legal_name='Proveedor sin especialidad')
    assert provider.default_expense_category_id is None
    for url in ('/providers/new', f'/providers/{provider.id}/edit', '/expenses/new'):
        html = client.get(url).text
        assert 'Categoría de gasto predeterminada' in html
        assert 'Se propondrá automáticamente al registrar gastos de este proveedor. Podrás cambiarla en cada gasto.' in html
        assert 'Categoría habitual' not in html
    assert 'Categoría de gasto predeterminada' in client.get(f'/providers/{provider.id}').text


def test_expense_override_preserves_active_provider_default(db_session):
    cleaning = service.save(db_session, name='Limpieza')
    repair = service.save(db_session, name='Reparación')
    provider = ProviderService().save(db_session, legal_name='Empresa sintética', default_expense_category_id=cleaning.id)
    prop = Property(name='Finca de prueba', address='Calle de prueba', city='Elche', owner='')
    db_session.add(prop); db_session.commit()
    expense = ExpenseService().create(db_session, property_id=prop.id, provider_id=provider.id, category_id=repair.id,
                                     expense_date=date(2026,9,1), concept='Trabajo excepcional', base_amount='10', vat_rate='0', withholding_rate='0')
    db_session.refresh(provider)
    assert expense.category_id == repair.id
    assert provider.default_expense_category_id == cleaning.id


def test_compact_category_table_and_edit_state_preservation(client, db_session):
    cat = service.save(db_session, name='Categoría apagada', description='Descripción solo en edición', active=False)
    html = client.get('/providers/categories').text
    table = html.split('<table', 1)[1].split('</table>', 1)[0]
    assert 'Categoría</th>' in table and 'Orden</th>' in table and 'Activa</th>' in table
    assert 'Descripción' not in table and 'Estado</th>' not in table and 'Acciones</th>' not in table
    assert '<button' not in table and 'rm-switch-input' in table
    assert 'aria-checked="false"' in table and 'Activar categoría Categoría apagada' in table
    assert 'text-secondary' in table and f'/providers/categories/{cat.id}/edit' in table
    edit = client.get(f'/providers/categories/{cat.id}/edit').text
    assert 'Descripción solo en edición' in edit and 'name="active"' not in edit
    # Even a stale/forged form value must not reactivate a category.
    client.post(f'/providers/categories/{cat.id}/edit', data={'name':'Renombrada','description':'Conservada','active':'1'})
    db_session.refresh(cat)
    assert not cat.active and cat.description == 'Conservada'


def test_category_switch_json_persistence_and_invalid_request(client, db_session):
    cat = service.save(db_session, name='Prueba switch')
    for flag in ('0', '1'):
        response = client.post(f'/providers/categories/{cat.id}/active', data={'active':flag}, headers={'Accept':'application/json'})
        assert response.status_code == 200 and response.json() == {'active':flag=='1'}
        db_session.refresh(cat)
        assert cat.active == (flag == '1')
    assert client.post(f'/providers/categories/{cat.id}/active',data={'active':'invalid'},headers={'Accept':'application/json'}).status_code == 400
    db_session.refresh(cat)
    assert cat.active


def test_provider_compact_list_keeps_full_detail_and_switch(client, db_session):
    cat = service.save(db_session, name='Limpieza')
    name = 'Limpiezas y Servicios de Demostración con Nombre Largo S.L.'
    p = ProviderService().save(db_session, legal_name=name, tax_id='TEST-FISCAL',
                              address_line='Dirección sintética', city='Ciudad de prueba',
                              email='proveedor@example.invalid', phone='+34000000000',
                              notes='Observación sintética', default_expense_category_id=cat.id)
    html = client.get('/providers').text
    table = html.split('<table',1)[1].split('</table>',1)[0]
    assert 'Proveedor</th>' in table and 'Predeterminada</th>' in table and 'Activo</th>' in table
    for hidden in ('NIF/CIF', 'Concepto', 'Contacto', 'Estado', 'TEST-FISCAL', 'proveedor@example.invalid', '+34000000000', 'Dirección sintética'):
        assert hidden not in table
    assert name in table and f'href="/providers/{p.id}"' in table and 'data-provider-active' in table
    detail = client.get(f'/providers/{p.id}').text
    for visible in ('TEST-FISCAL','proveedor@example.invalid','+34000000000','Dirección sintética','Observación sintética','IBAN','Categoría de gasto predeterminada'):
        assert visible in detail
    for flag in ('0','1'):
        response = client.post(f'/providers/{p.id}/active',data={'active':flag},headers={'Accept':'application/json'})
        assert response.json() == {'active':flag=='1'}
        db_session.refresh(p)
        assert p.active == (flag=='1') and p.default_expense_category_id == cat.id
        html = client.get('/providers').text
        assert f'aria-checked="{str(p.active).lower()}"' in html
        if not p.active:
            assert 'data-provider-name class="text-secondary"' in html
            assert client.get(f'/providers/{p.id}').status_code == 200
    assert client.post(f'/providers/{p.id}/active',data={'active':'bad'},headers={'Accept':'application/json'}).status_code == 400
    db_session.refresh(p)
    assert p.active and p.tax_id == 'TEST-FISCAL'
