"""Synthetic reconciliation cases only; no private backup/identities needed."""
from datetime import date
from decimal import Decimal
from copy import deepcopy
import re

import pytest
from sqlalchemy import select,func
from backend.models import Person,Property,Room,Booking,BookingParty,BookingFinancialTerms,BookingCharge,Payment,SepaMandate,Owner
from backend.models.migration_audit import MigrationRun,MigrationAction
from backend.services.netfincas_source import Snapshot,digest
from backend.services.netfincas_reconciliation import ReconciliationService,category,source_iban

IBAN='ES9121000418450200051332'  # Public checksum example, not source/customer data.
TODAY=date(2026,9,11)


def source_tables():
    person=dict(CODIGO='101',APEYNOM='Ana Prueba Uno',NIF='TEST-DOC-101',MAIL='ana@example.test',TEL='600000001',FAX='600000099',DIR='Calle Ensayo',DIRNUM='10',POB='Ciudad Prueba',CP='00000',PROVINCIA='Provincia',IBAN=IBAN[:4],BANCO=IBAN[4:8],SUCURSAL=IBAN[8:12],DC=IBAN[12:14],CUENTA=IBAN[14:],TITULAR=None)
    unit=dict(CODIGO='201',CODFINCA='301',CODINQUILINO1='101',CODPAGADOR='101',FECHAINICIO='1-SEP-2026',FECHAVENCIMIENTO='1-JUL-2027',FECHA_ULT_RECIBO='8-SEP-2026',VACIO='N',RENTA='400.00',FIANZA=None,FIANZA_IMPORTE='450.00',DIRLETRA='1',REFDOMICI='SYNTH-REF',FECHA_MANDATO='1-SEP-2026')
    return {'ALQ_INQUILINOS':[person],'ALQ_INQUILINOS_H':[],'ALQ_INMUEBLES':[unit],
        'ALQ_FINCAS':[dict(CODIGO='301',DIR='Calle Ensayo',DIRNUM='10',POB='Ciudad Prueba',CODPROPIETARIO='401')],
        'ALQ_PROPIETARIOS':[dict(CODIGO='401',APEYNOM='Propietario Sintético',NIF='TEST-OWNER')],
        'ALQ_INMUEBLES_INDIVISOS':[],'COMUN_BANCOS':[]}


class SyntheticSource:
    def __init__(self,tables=None):self.tables=tables or source_tables()
    def read(self):return Snapshot(deepcopy(self.tables),digest(self.tables))


@pytest.fixture
def nf(db_session,monkeypatch):
    monkeypatch.setattr('backend.services.netfincas_reconciliation.business_today',lambda:TODAY)
    p=Property(name='Finca prueba',street='Calle Ensayo',street_number='10',address='Calle Ensayo 10',city='Ciudad Prueba',owner='Prueba')
    db_session.add(p);db_session.flush()
    r=Room(property_id=p.id,code='Prueba01',active=True,operational_since=date(2026,1,1))
    person=Person(full_name='Ana Prueba Uno',active=True,source='manual',verification_status='unverified')
    db_session.add_all([r,person]);db_session.flush()
    b=Booking(room_id=r.id,check_in=date(2026,9,1),check_out=date(2027,7,1),origin='manual')
    db_session.add(b);db_session.flush();db_session.add(BookingParty(booking_id=b.id,person_id=person.id,role='unclassified'));db_session.commit()
    return ReconciliationService(),SyntheticSource(),person,b,r


def count(db,model):return db.scalar(select(func.count()).select_from(model))


def fields(person,**kw):return dict(kind='person_fields',source_id='101',target_id=person.id,fields=['email'],**kw)


def test_strong_missing_fields_fax_masked_and_fianza(db_session,nf):
    svc,src,p,b,r=nf;review=svc.review(db_session,src.read())
    row=review['people'][0];assert row['state']=='Coincidencia fuerte'
    assert any('Misma unidad' in reason for reason in row['matches'][0]['reasons'])
    assert row['source']['FAX']=='600000099'
    assert all(f['key']!='FAX' for f in row['fields'])
    assert next(f for f in row['fields'] if f['key']=='email')['status']=='Falta en RentalManager'
    assert IBAN not in str(row['fields'])
    assert review['contracts'][0]['source']['FIANZA_IMPORTE']=='450.00'
    assert review['sepa'][0]['eligible'] is False
    assert review['sepa'][0]['warning']=='Titular de cuenta no identificado'


def test_probable_and_ambiguous_not_name_auto_merge(db_session,nf):
    svc,src,p,b,r=nf
    src.tables['ALQ_INMUEBLES']=[]
    assert svc.review(db_session,src.read())['people'][0]['state']=='Probable'
    db_session.add(Person(full_name=p.full_name,source='manual',active=True));db_session.commit()
    assert svc.review(db_session,src.read())['people'][0]['state']=='Ambiguo'


@pytest.mark.parametrize('end,empty,expected',[('1-JUL-2026','N','Posible prórroga / requiere revisión'),('1-JUL-2026','S','Vencido y vacío'),('1-JUL-2027','S','Vigente pero vacío'),('bad','N','Ambiguo')])
def test_category(end,empty,expected):
    u=source_tables()['ALQ_INMUEBLES'][0];u.update(FECHAINICIO='1-SEP-2025',FECHAVENCIMIENTO=end,VACIO=empty)
    assert category(u,TODAY)==expected


def test_future():
    u=source_tables()['ALQ_INMUEBLES'][0];u['FECHAINICIO']='1-OCT-2026'
    assert category(u,TODAY)=='Futuro'


def test_dry_run_no_writes_field_selection_and_idempotent_apply(db_session,nf):
    svc,src,p,b,r=nf;plan=svc.plan(db_session,src.read(),[fields(p)])
    assert p.email is None and count(db_session,MigrationRun)==0 and not db_session.new
    run=svc.apply(db_session,src.read(),plan)
    assert svc.apply(db_session,src.read(),plan)==run
    db_session.refresh(p);assert p.email=='ana@example.test' and p.phone is None and p.iban is None
    assert count(db_session,MigrationAction)==1
    action=db_session.scalar(select(MigrationAction));assert action.field=='email'


def test_conflict_not_overwritten(db_session,nf):
    svc,src,p,b,r=nf;p.email='existing@example.test';db_session.commit()
    review=svc.review(db_session,src.read());assert next(f for f in review['people'][0]['fields'] if f['key']=='email')['conflict']
    plan=svc.plan(db_session,src.read(),[fields(p)])
    assert not plan.actions and plan.skipped and p.email=='existing@example.test'


def test_source_and_destination_stale(db_session,nf):
    svc,src,p,b,r=nf;plan=svc.plan(db_session,src.read(),[fields(p)])
    src.tables['ALQ_INQUILINOS'][0]['MAIL']='changed@example.test'
    with pytest.raises(ValueError,match='ha cambiado'):svc.apply(db_session,src.read(),plan)
    plan=svc.plan(db_session,src.read(),[fields(p)])
    p.email='concurrent@example.test';db_session.commit()
    with pytest.raises(ValueError,match='ha cambiado'):svc.apply(db_session,src.read(),plan)
    assert count(db_session,MigrationRun)==0


def test_rollback_on_second_action(db_session,nf,monkeypatch):
    svc,src,p,b,r=nf;selection=fields(p);selection['fields']=['email','phone']
    src.tables['ALQ_INQUILINOS'][0]['FAX']=None
    plan=svc.plan(db_session,src.read(),[selection]);original=db_session.flush;calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        if len(calls)==3:raise RuntimeError('Synthetic fault')
        return original(*args,**kwargs)
    monkeypatch.setattr(db_session,'flush',fail)
    with pytest.raises(RuntimeError):svc.apply(db_session,src.read(),plan)
    monkeypatch.setattr(db_session,'flush',original)
    db_session.refresh(p);assert p.email is None and p.phone is None and count(db_session,MigrationRun)==0


def test_fax_rejected_and_extension_never_changes_booking(db_session,nf):
    svc,src,p,b,r=nf;s=fields(p);s['fields']=['FAX']
    with pytest.raises(ValueError):svc.plan(db_session,src.read(),[s])
    src.tables['ALQ_INMUEBLES'][0]['FECHAVENCIMIENTO']='1-JUL-2026'
    plan=svc.plan(db_session,src.read(),[dict(kind='extension_review',source_id='201')])
    assert not plan.actions and plan.skipped
    assert b.check_out==date(2027,7,1)
    with pytest.raises(ValueError):svc.plan(db_session,src.read(),[dict(kind='terms',source_id='201',target_id=b.id,context_confirmed=True,due_day=1)])


def test_terms_draft_only_and_no_ledger_or_sepa(db_session,nf):
    svc,src,p,b,r=nf
    plan=svc.plan(db_session,src.read(),[dict(kind='terms',source_id='201',target_id=b.id,context_confirmed=True,due_day=3,include_deposit=True)])
    svc.apply(db_session,src.read(),plan)
    t=db_session.scalar(select(BookingFinancialTerms));assert t.status=='draft' and t.monthly_rent==Decimal('400') and t.deposit_agreed==Decimal('450')
    assert count(db_session,BookingCharge)==count(db_session,Payment)==count(db_session,SepaMandate)==0
    with pytest.raises(ValueError):svc.plan(db_session,src.read(),[dict(kind='terms',source_id='201',target_id=b.id,context_confirmed=True,due_day=1)])


def test_new_person_requires_current_contract_and_no_roles(db_session,nf):
    svc,src,p,b,r=nf;src.tables['ALQ_INQUILINOS'][0]['APEYNOM']='Otra Identidad Sintética'
    plan=svc.plan(db_session,src.read(),[dict(kind='person_create',source_id='101',fields=['email'],identity_confirmed=True)]);svc.apply(db_session,src.read(),plan)
    assert count(db_session,Person)==2 and count(db_session,BookingParty)==1
    with pytest.raises(ValueError):svc.plan(db_session,src.read(),[dict(kind='person_create',source_id='101',fields=[])])


def test_booking_create_explicit_no_overlap_and_unclassified(db_session,nf):
    svc,src,p,b,r=nf;s=dict(kind='booking_create',source_id='201',room_id=r.id,person_id=p.id,context_confirmed=True,half_open_confirmed=True)
    with pytest.raises(ValueError,match='solapada'):svc.plan(db_session,src.read(),[s])
    src.tables['ALQ_INMUEBLES'][0].update(FECHAINICIO='1-AUG-2027',FECHAVENCIMIENTO='1-SEP-2027')
    plan=svc.plan(db_session,src.read(),[s]);svc.apply(db_session,src.read(),plan)
    assert count(db_session,Booking)==2 and count(db_session,BookingParty)==2 and count(db_session,Payment)==0


def test_routes_disabled_by_default(client):
    assert client.get('/reconciliation/netfincas').status_code==404


def enable(client,db,src):
    client.app.state.netfincas_enabled=True;client.app.state.netfincas_source=src
    client.app.state.netfincas_apply_database=db.get_bind().url.database


def form_tokens(html):return {key:re.search(fr'name="{key}" value="([^"]+)"',html).group(1) for key in ['csrf','token']}


def test_admin_render_privacy_and_csrf(client,db_session,nf):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    res=client.get('/reconciliation/netfincas');assert res.status_code==200
    assert IBAN not in res.text and 'data/runtime' not in res.text
    assert 'FAX NetFincas' in res.text and 'FIANZA_IMPORTE' in res.text
    assert res.headers['cache-control']=='no-store'
    assert client.post('/reconciliation/netfincas/dry-run',data={}).status_code==403
    f=form_tokens(res.text);f.update(person_select='101',person_target_101=str(p.id),person_fields_101='email')
    preview=client.post('/reconciliation/netfincas/dry-run',data=f)
    assert 'ACTUALIZAR' in preview.text and p.email is None
    apply=form_tokens(preview.text);apply['confirm']='yes'
    assert 'Selección aplicada' in client.post('/reconciliation/netfincas/apply',data=apply).text
    assert count(db_session,MigrationAction)==1
    assert 'Person' in client.get('/reconciliation/netfincas/runs').text


@pytest.mark.parametrize('site,status', [('same-origin',200),('cross-site',403),('',403)])
def test_no_referrer_form_origin(client,db_session,nf,site,status):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    f=form_tokens(client.get('/reconciliation/netfincas').text)
    response=client.post('/reconciliation/netfincas/dry-run',data=f,
        headers={'Origin':'null','Sec-Fetch-Site':site})
    assert response.status_code==status


def test_apply_database_guard(client,db_session,nf):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    res=client.get('/reconciliation/netfincas');f=form_tokens(res.text)
    client.app.state.netfincas_apply_database='some_other_database.db'
    f['confirm']='yes';assert client.post('/reconciliation/netfincas/apply',data=f).status_code==403


def test_iban_source_checksum_and_public_app_no_route():
    assert source_iban(source_tables()['ALQ_INQUILINOS'][0])==IBAN
    from backend.public_main import app
    assert not any(getattr(r,'path','').startswith('/reconciliation') for r in app.routes)


def test_owner_create_no_relationships(db_session,nf):
    svc,src,p,b,r=nf;plan=svc.plan(db_session,src.read(),[dict(kind='owner_create',source_id='401')])
    svc.apply(db_session,src.read(),plan);assert count(db_session,Owner)==1


def test_no_iban_values_in_audit(db_session,nf):
    svc,src,p,b,r=nf;s=fields(p);s['fields']=['iban']
    plan=svc.plan(db_session,src.read(),[s]);svc.apply(db_session,src.read(),plan)
    assert p.iban==IBAN
    for item in db_session.scalars(select(MigrationAction)):
        assert IBAN not in str(vars(item))


def test_compare_disables_conflict_and_requires_strong_iban(client,db_session,nf):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    src.tables['ALQ_INQUILINOS'][0]['FAX']=None  # Isolate RM/source conflict from multiple source numbers.
    p.phone='600000008';db_session.commit()
    page=client.get('/reconciliation/netfincas')
    assert 'Datos completables' in page.text and 'Revisar cambios' in page.text
    assert 'checked' not in page.text
    f=form_tokens(page.text);f.update(source_id='101',target_id=str(p.id))
    values={x['key']:x for x in client.post('/reconciliation/netfincas/compare',data=f).json()['fields']}
    assert values['email']['selectable'] and values['iban']['selectable']
    assert not values['phone']['selectable'] and values['phone']['status']=='Diferente'
    assert IBAN not in str(values) and 'TEST-DOC-101' not in str(values)
    src.tables['ALQ_INMUEBLES']=[]
    selected=fields(p);selected['fields']=['iban']
    with pytest.raises(ValueError,match='coincidencia fuerte'):svc.plan(db_session,src.read(),[selected])


def test_ambiguous_new_person_requires_additional_confirmation(db_session,nf):
    svc,src,p,b,r=nf
    src.tables['ALQ_INQUILINOS'][0]['APEYNOM']='Ana Prueba Dos'
    with pytest.raises(ValueError,match='confirmar expresamente'):
        svc.plan(db_session,src.read(),[dict(kind='person_create',source_id='101',fields=[])])


def test_owner_selected_fields_only_and_no_overwrite(db_session,nf):
    svc,src,p,b,r=nf
    owner=Owner(legal_name='Propietario Sintético',phone='600000002');db_session.add(owner);db_session.commit()
    src.tables['ALQ_PROPIETARIOS'][0].update(MAIL='owner@example.test',TEL='600000003')
    plan=svc.plan(db_session,src.read(),[dict(kind='owner_fields',source_id='401',target_id=owner.id,fields=['email','phone'])])
    assert len(plan.actions)==1 and plan.skipped
    svc.apply(db_session,src.read(),plan);db_session.refresh(owner)
    assert owner.email=='owner@example.test' and owner.phone=='600000002' and owner.tax_id is None


def test_review_summary_masked_no_write(client,db_session,nf):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    f=form_tokens(client.get('/reconciliation/netfincas').text)
    f.update(person_select='101',person_target_101=str(p.id),person_fields_101=['email','iban'])
    page=client.post('/reconciliation/netfincas/dry-run',data=f)
    assert page.status_code==200 and '2 campos a completar' in page.text
    assert p.full_name in page.text and 'NO SE MODIFICARÁN' in page.text
    assert 'Aplicar cambios' in page.text and IBAN not in page.text
    assert count(db_session,MigrationRun)==0 and p.email is None and p.iban is None


def test_fax_phone_review_and_selective_apply(client,db_session,nf):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    src.tables['ALQ_INQUILINOS'][0].update(TEL=None,FAX='  +39  333-1234567  ')
    f=form_tokens(client.get('/reconciliation/netfincas').text)
    compare=dict(f,source_id='101',target_id=str(p.id))
    values={x['key']:x for x in client.post('/reconciliation/netfincas/compare',data=compare).json()['fields']}
    assert values['phone']['selectable'] and values['phone']['source']=='+39 333-1234567'
    f.update(person_select='101',person_target_101=str(p.id),person_fields_101='phone')
    preview=client.post('/reconciliation/netfincas/dry-run',data=f)
    assert 'Valor original NetFincas' in preview.text and 'FAX' in preview.text
    assert p.phone is None and count(db_session,MigrationRun)==0
    apply=form_tokens(preview.text);apply['confirm']='yes'
    assert 'Selección aplicada' in client.post('/reconciliation/netfincas/apply',data=apply).text
    db_session.refresh(p);assert p.phone=='+39 333-1234567' and p.email is None
    audit=db_session.scalar(select(MigrationAction))
    assert audit.source_id=='person:101:FAX' and audit.field=='phone'
    assert '333-1234567' not in repr(vars(audit))


def test_phone_conflict_rejected_and_existing_protected(db_session,nf):
    svc,src,p,b,r=nf;s=fields(p);s['fields']=['phone']
    with pytest.raises(ValueError):svc.plan(db_session,src.read(),[s])
    src.tables['ALQ_INQUILINOS'][0]['TEL']=None
    p.phone='+34 647 123 456';db_session.commit()
    plan=svc.plan(db_session,src.read(),[s])
    assert not plan.actions and plan.skipped and p.phone=='+34 647 123 456'


def test_mobile_physical_fax_empty_phone_candidate(client,db_session,nf):
    # Structure of the reported case; all identity/phone values remain synthetic.
    svc,src,p,b,r=nf;enable(client,db_session,src)
    src.tables['ALQ_INQUILINOS'][0].update(TEL=None,FAX='+39 3331234567',_phone_mobile_field='FAX')
    page=client.get('/reconciliation/netfincas')
    assert 'Móvil NetFincas' in page.text
    f=form_tokens(page.text);f.update(source_id='101',target_id=str(p.id))
    phone=next(x for x in client.post('/reconciliation/netfincas/compare',data=f).json()['fields'] if x['key']=='phone')
    assert phone['source']=='+39 3331234567' and phone['selectable']
    assert p.phone is None and count(db_session,MigrationRun)==0


def test_choose_distinct_phone_dry_run_apply_and_stale(client,db_session,nf):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    row=src.tables['ALQ_INQUILINOS'][0]
    row.update(TEL='+34 647123456',FAX='+39 3331234567',_phone_mobile_field='FAX')
    page=client.get('/reconciliation/netfincas')
    assert 'data-nf-phone-source' in page.text and 'sin selección automática' in page.text
    f=form_tokens(page.text);f.update(source_id='101',target_id=str(p.id),phone_source='FAX')
    phone=next(x for x in client.post('/reconciliation/netfincas/compare',data=f).json()['fields'] if x['key']=='phone')
    assert phone['selectable'] and phone['source']==row['FAX']
    f.update(person_select='101',person_target_101=str(p.id),person_fields_101='phone',phone_source_101='FAX')
    preview=client.post('/reconciliation/netfincas/dry-run',data=f)
    assert '1 campos a completar' in preview.text and p.phone is None
    selected=dict(kind='person_fields',source_id='101',target_id=p.id,fields=['phone'],phone_source='FAX')
    plan=svc.plan(db_session,src.read(),[selected])
    p.phone='+34 647123457';db_session.commit()
    with pytest.raises(ValueError):svc.apply(db_session,src.read(),plan)
    assert p.phone=='+34 647123457' and count(db_session,MigrationRun)==0
    p.phone=None;db_session.commit()
    plan=svc.plan(db_session,src.read(),[selected]);svc.apply(db_session,src.read(),plan)
    db_session.refresh(p);assert p.phone==row['FAX']
    assert db_session.scalar(select(MigrationAction)).source_id=='person:101:FAX'


def test_country_informational_not_selectable(client,db_session,nf):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    src.tables['ALQ_INQUILINOS'][0].update(PAIS='ESPAÑA',DIRSIGLA='VIA',DIR='STRADA TEST')
    page=client.get('/reconciliation/netfincas')
    assert 'dato no verificado' in page.text and 'Dato informativo no fiable' in page.text
    assert 'value="country"' not in page.text and 'data-nf-field="country"' not in page.text
    f=form_tokens(page.text);f.update(source_id='101',target_id=str(p.id))
    assert 'country' not in {x['key'] for x in client.post('/reconciliation/netfincas/compare',data=f).json()['fields']}
    f.update(person_select='101',person_target_101=str(p.id),person_fields_101=['country'])
    preview=client.post('/reconciliation/netfincas/dry-run',data=f)
    assert 'Selección no aplicable' in preview.text and count(db_session,MigrationRun)==0


@pytest.mark.parametrize('existing',[None,'GB'])
def test_import_preserves_country_and_other_fields(db_session,nf,existing):
    svc,src,p,b,r=nf;p.country=existing;db_session.commit()
    row=src.tables['ALQ_INQUILINOS'][0];row.update(PAIS='ESPAÑA',DIRSIGLA='VIA',DIR='STRADA TEST')
    before=svc.review(db_session,src.read())['people'][0]['matches']
    scores=[(m['target'].id,m['score']) for m in before]
    row['PAIS']='ITALIA'
    assert scores==[(m['target'].id,m['score']) for m in svc.review(db_session,src.read())['people'][0]['matches']]
    plan=svc.plan(db_session,src.read(),[dict(kind='person_fields',source_id='101',target_id=p.id,fields=['email','address_line'])])
    assert all('country' not in a.values for a in plan.actions)
    svc.apply(db_session,src.read(),plan);db_session.refresh(p)
    assert p.country==existing and p.email and p.address_line.startswith('VIA STRADA TEST')


def test_old_country_plan_cannot_apply(db_session,nf):
    from backend.services.netfincas_reconciliation import Action
    svc,src,p,b,r=nf
    with pytest.raises(ValueError):
        svc.plan(db_session,src.read(),[dict(kind='person_fields',source_id='101',target_id=p.id,fields=['country'])])
    plan=svc.plan(db_session,src.read(),[dict(kind='person_fields',source_id='101',target_id=p.id,fields=['email'])])
    plan.actions.append(Action('person:101','Person',p.id,'complete','country',{'country':'ES'}))
    with pytest.raises(ValueError,match='no importable'):svc.apply(db_session,src.read(),plan)
    assert p.country is None and p.email is None and count(db_session,MigrationRun)==0


@pytest.mark.parametrize('existing',[False,True])
def test_owner_mobile_selective_and_protected(db_session,nf,existing):
    svc,src,p,b,r=nf
    owner=Owner(legal_name='Owner Test',phone='+34647123456' if existing else None);db_session.add(owner);db_session.commit()
    src.tables['ALQ_PROPIETARIOS'][0].update(_phone_entity='ALQ_PROPIETARIOS',TEL=None,FAX='+39 3331234567')
    s=dict(kind='owner_fields',source_id='401',target_id=owner.id,fields=['phone'])
    plan=svc.plan(db_session,src.read(),[s])
    if existing:
        assert not plan.actions and plan.skipped and owner.phone=='+34647123456'
    else:
        assert plan.actions[0].source_field=='FAX'
        svc.apply(db_session,src.read(),plan);db_session.refresh(owner)
        assert owner.phone=='+39 3331234567'


def test_owner_distinct_requires_choice(client,db_session,nf):
    svc,src,p,b,r=nf;enable(client,db_session,src)
    owner=Owner(legal_name='Owner Test');db_session.add(owner);db_session.commit()
    src.tables['ALQ_PROPIETARIOS'][0].update(_phone_entity='ALQ_PROPIETARIOS',TEL='+34647123456',FAX='+393331234567')
    s=dict(kind='owner_fields',source_id='401',target_id=owner.id,fields=['phone'])
    with pytest.raises(ValueError):svc.plan(db_session,src.read(),[s])
    page=client.get('/reconciliation/netfincas')
    assert 'data-nf-owner-phone-source' in page.text and 'Móvil NetFincas' in page.text
    f=form_tokens(page.text);f.update(owner_select='401',owner_action_401='owner_fields',owner_target_401=str(owner.id),owner_fields_401='phone',owner_phone_source_401='FAX')
    preview=client.post('/reconciliation/netfincas/dry-run',data=f)
    assert '1 campos a completar' in preview.text and owner.phone is None and count(db_session,MigrationRun)==0
    s['phone_source']='FAX';plan=svc.plan(db_session,src.read(),[s])
    svc.apply(db_session,src.read(),plan);assert owner.phone=='+393331234567'
