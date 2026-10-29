from copy import deepcopy
from datetime import date
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from backend.models.fee_billing import *
from backend.services.fee_invoice_service import FeeInvoiceService
from backend.services.billing_settlement_service import BillingSettlementService
from tests.integration.api.test_fee_billing_flow import billing_env, prop, receipt, drafts


def setup_invoice(db, owner, vat='21', withholding='15'):
    p,_=prop(db,owner,vat=vat,withholding=withholding)
    receipt(db,p,'1520')
    settlement=drafts(db,[p])[0]
    BillingSettlementService().close(db,settlement.id,settlement.fingerprint)
    issuer=InvoiceIssuerProfile(identity=dict(name='Emisor de pruebas',tax_id='89890001K',
        address='Calle Sintética 1',postal_code='03001',city='Elche',province='Alicante',country='ES',
        identification_type='NIF',system=dict(name='RentalManager TEST',id='RM',version='test-1',
        installation='synthetic-01',producer_name='Fabricante sintético',producer_nif='89890001K')))
    db.add(issuer);db.flush()
    series=InvoiceSeries(issuer_id=issuer.id,prefix='TEST-HON-2026-',name='Pruebas',fiscal_year=2026)
    db.add_all([series,OwnerFiscalIdentity(owner_id=owner.id,identification_type='NIF',identification_country='ES')]);db.commit()
    return settlement,series


def issue(db,settlement,series):
    s=FeeInvoiceService();v=s.preview(db,settlement.id,series.id,date(2026,9,30))
    assert not v['warnings'],v['warnings']
    invoice=s.draft(db,settlement.id,series.id,date(2026,9,30),v['fingerprint'],str(uuid4()))
    return s.issue(db,invoice.id,invoice.fingerprint)


def test_preview_issue_gross_net_idempotency_snapshot_pdf(db_session,billing_env):
    settlement,series=setup_invoice(db_session,billing_env)
    s=FeeInvoiceService();view=s.preview(db_session,settlement.id,series.id,date(2026,9,30))
    assert series.counter==0 and 'number' not in view
    assert view['fee_base']=='304.00' and view['fee_vat']=='63.84'
    assert view['fee_withholding']=='45.60' and view['gross_invoice_total']=='367.84' and view['net_payable']=='322.24'
    before=db_session.scalar(select(func.count()).select_from(FeeCompensation))
    invoice=issue(db_session,settlement,series)
    frozen=deepcopy(invoice.snapshot)
    assert invoice.number=='TEST-HON-2026-000001'
    assert s.issue(db_session,invoice.id,invoice.fingerprint).id==invoice.id
    assert db_session.scalar(select(func.count()).select_from(FeeCompensation))==before
    assert db_session.get(InvoiceSeries,series.id).counter==1
    billing_env.legal_name='Nombre cambiado después';db_session.commit()
    assert invoice.snapshot==frozen
    record=db_session.scalar(select(InvoiceFiscalRecord))
    assert record.payload['ImporteTotal']=='367.84' and record.payload['CuotaTotal']=='63.84'
    assert 'importe=367.84' in invoice.snapshot['qr_url']
    from backend.services.fee_invoice_pdf import render_invoice
    assert render_invoice(invoice.snapshot).startswith(b'%PDF')


def test_stale_draft_does_not_consume_number(db_session,billing_env):
    settlement,series=setup_invoice(db_session,billing_env)
    s=FeeInvoiceService();view=s.preview(db_session,settlement.id,series.id,date(2026,9,30))
    item=s.draft(db_session,settlement.id,series.id,date(2026,9,30),view['fingerprint'],str(uuid4()))
    billing_env.city='Otra localidad';db_session.commit()
    with pytest.raises(ValueError,match='desactualizados'):s.issue(db_session,item.id,item.fingerprint)
    assert db_session.get(InvoiceSeries,series.id).counter==0
    assert db_session.scalar(select(func.count()).select_from(InvoiceFiscalRecord))==0


def test_outbox_local_retry_no_duplicate_records(db_session,billing_env):
    settlement,series=setup_invoice(db_session,billing_env);issue(db_session,settlement,series)
    s=FeeInvoiceService();out=db_session.scalar(select(FiscalSubmission))
    for outcome in ('unknown','retry_pending','accepted','accepted'):
        s.mock_submission(db_session,out.id,outcome)
    assert out.attempts==3 and out.status=='accepted'
    assert db_session.scalar(select(func.count()).select_from(FiscalSubmissionAttempt))==3
    assert db_session.scalar(select(func.count()).select_from(InvoiceFiscalRecord))==1


def test_foreign_owner_explicit_and_missing_data_blocks(db_session,billing_env):
    settlement,series=setup_invoice(db_session,billing_env)
    identity=db_session.get(OwnerFiscalIdentity,billing_env.id)
    identity.identification_type='03';identity.identification_country='IT'
    billing_env.tax_id='SYNTHETIC123';billing_env.country='IT';db_session.commit()
    assert not FeeInvoiceService().preview(db_session,settlement.id,series.id,date(2026,9,30))['warnings']
    billing_env.address_line=None;db_session.commit()
    s=FeeInvoiceService();v=s.preview(db_session,settlement.id,series.id,date(2026,9,30))
    assert v['warnings']
    item=s.draft(db_session,settlement.id,series.id,date(2026,9,30),v['fingerprint'],str(uuid4()))
    with pytest.raises(ValueError,match='dato fiscal'):s.issue(db_session,item.id,item.fingerprint)


def test_configuration_preview_invoice_pages(client,db_session,billing_env):
    settlement,series=setup_invoice(db_session,billing_env)
    for path in ('/settings/invoicing','/settings/invoicing?tab=series','/settings/invoicing?tab=tax',
                 f'/settlements/{settlement.id}',
                 f'/settlements/{settlement.id}/invoice?series_id={series.id}&issue_date=2026-09-30'):
        response=client.get(path);assert response.status_code==200,(path,response.text[:200])
    item=issue(db_session,settlement,series)
    assert client.get(f'/invoices/{item.id}').status_code==200
    assert client.get(f'/invoices/{item.id}/pdf').headers['content-type']=='application/pdf'


def test_database_guards_and_refund_rectification(db_session,billing_env):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from backend.models import Payment,PaymentAllocation
    from datetime import datetime
    settlement,series=setup_invoice(db_session,billing_env)
    invoice=issue(db_session,settlement,series);frozen=deepcopy(invoice.snapshot)
    with pytest.raises(IntegrityError,match='immutable'):
        db_session.execute(text('UPDATE management_fee_invoices SET number=number WHERE id=:id'),{'id':invoice.id})
    db_session.rollback()
    original=db_session.scalar(select(PaymentAllocation))
    refund=Payment(booking_id=original.payment.booking_id,amount=original.amount,effective_date=date(2026,10,10),
        direction='refund',method='cash',lifecycle='posted',posted_at=datetime(2026,10,10),corrects_payment_id=original.payment_id)
    db_session.add(refund);db_session.flush()
    db_session.add(PaymentAllocation(payment_id=refund.id,charge_id=original.charge_id,amount=original.amount));db_session.commit()
    assert FeeInvoiceService().summary(db_session,settlement.id)['rectification_pending']
    from backend.models import Property
    p=db_session.get(Property,invoice.snapshot['lines'][0]['property_id'])
    correction=drafts(db_session,[p],date(2026,10,1),date(2026,11,1))[0]
    BillingSettlementService().close(db_session,correction.id,correction.fingerprint)
    assert FeeInvoiceService().summary(db_session,settlement.id)['rectification_pending']
    assert invoice.snapshot==frozen
    assert correction.snapshot['totals']['payout_due']=='0.00'
    assert FeeInvoiceService().preview(db_session,correction.id,series.id,date(2026,10,31))['warnings']


def test_issue_rollback_after_counter_and_concurrent_retry(db_session,billing_env,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    settlement,series=setup_invoice(db_session,billing_env)
    s=FeeInvoiceService();v=s.preview(db_session,settlement.id,series.id,date(2026,9,30))
    item=s.draft(db_session,settlement.id,series.id,date(2026,9,30),v['fingerprint'],str(uuid4()))
    import backend.services.fee_invoice_service as module
    original=module.alta_hash
    def fail(*args): raise RuntimeError('injected')
    monkeypatch.setattr(module,'alta_hash',fail)
    with pytest.raises(RuntimeError,match='injected'):s.issue(db_session,item.id,item.fingerprint)
    assert db_session.get(InvoiceSeries,series.id).counter==0
    monkeypatch.setattr(module,'alta_hash',original)
    engine=db_session.get_bind();item_id=item.id;fp=item.fingerprint;db_session.rollback()
    def worker(_):
        with Session(engine) as session:return s.issue(session,item_id,fp).number
    with ThreadPoolExecutor(max_workers=2) as pool: numbers=list(pool.map(worker,range(2)))
    assert numbers==['TEST-HON-2026-000001']*2
    assert db_session.get(InvoiceSeries,series.id).counter==1


def test_chain_spans_series_and_owners_not_separate_chains(db_session,billing_env):
    from backend.models import Owner
    first,series=setup_invoice(db_session,billing_env);one=issue(db_session,first,series)
    other=Owner(legal_name='Otro propietario sintético',tax_id='89890001K',address_line='Calle Prueba 2',postal_code='03001',city='Elche',country='ES')
    db_session.add(other);db_session.flush()
    db_session.add(OwnerFiscalIdentity(owner_id=other.id,identification_type='NIF',identification_country='ES'))
    series2=InvoiceSeries(issuer_id=series.issuer_id,prefix='TEST-B-',name='Segunda');db_session.add(series2);db_session.commit()
    p,_=prop(db_session,other);receipt(db_session,p);second=drafts(db_session,[p])[0]
    BillingSettlementService().close(db_session,second.id,second.fingerprint);two=issue(db_session,second,series2)
    records=list(db_session.scalars(select(InvoiceFiscalRecord).order_by(InvoiceFiscalRecord.id)))
    assert len(records)==2 and records[0].chain_key==records[1].chain_key
    assert records[1].previous_record_id==records[0].id and records[1].payload['Huella']==records[0].hash
    assert db_session.scalar(select(func.count()).select_from(FiscalChainState))==1


def test_explicit_refresh_of_stale_draft_and_used_series_immutable(db_session,billing_env):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    settlement,series=setup_invoice(db_session,billing_env);s=FeeInvoiceService()
    v=s.preview(db_session,settlement.id,series.id,date(2026,9,30))
    draft=s.draft(db_session,settlement.id,series.id,date(2026,9,30),v['fingerprint'],str(uuid4()))
    billing_env.city='Ciudad revisada';db_session.commit()
    new=s.preview(db_session,settlement.id,series.id,date(2026,9,30))
    refreshed=s.draft(db_session,settlement.id,series.id,date(2026,9,30),new['fingerprint'],str(uuid4()))
    assert refreshed.id==draft.id and series.counter==0
    s.issue(db_session,refreshed.id,refreshed.fingerprint)
    with pytest.raises(IntegrityError,match='immutable'):
        db_session.execute(text('UPDATE invoice_series SET counter=0 WHERE id=:id'),{'id':series.id})
    db_session.rollback()


def test_fiscal_routes_fail_closed(client,monkeypatch):
    monkeypatch.setenv('INVOICING_ENABLED','false');monkeypatch.setenv('VERIFACTU_ENABLED','false')
    for path in ('/settings/invoicing','/invoices/1','/invoices/1/pdf','/settlements/1/invoice'):
        assert client.get(path).status_code==404


def test_public_routes_never_expose_fee_billing(db_session,billing_env):
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    app=create_public_app()
    with TestClient(app,base_url='http://localhost') as public:
        for path in ('/settings/invoicing','/invoices/1','/invoices/1/pdf','/settlements/1/invoice'):
            assert public.get(path).status_code==404


def test_taxpayer_number_unique_across_issuer_profile_versions(db_session,billing_env):
    settlement,series=setup_invoice(db_session,billing_env);first=issue(db_session,settlement,series)
    profile=db_session.get(InvoiceIssuerProfile,series.issuer_id)
    another=InvoiceIssuerProfile(identity=deepcopy(profile.identity));db_session.add(another);db_session.flush()
    newseries=InvoiceSeries(issuer_id=another.id,prefix=series.prefix,name='Versión errónea');db_session.add(newseries);db_session.commit()
    p,_=prop(db_session,billing_env,'Otra finca');receipt(db_session,p)
    second=drafts(db_session,[p])[0];BillingSettlementService().close(db_session,second.id,second.fingerprint)
    s=FeeInvoiceService();v=s.preview(db_session,second.id,newseries.id,date(2026,9,30))
    draft=s.draft(db_session,second.id,newseries.id,date(2026,9,30),v['fingerprint'],str(uuid4()))
    with pytest.raises(ValueError,match='Número ya emitido'):s.issue(db_session,draft.id,draft.fingerprint)
    assert db_session.get(InvoiceSeries,newseries.id).counter==0


def test_offline_xml_keeps_gross_and_exact_quotas(db_session,billing_env):
    from backend.core.verifactu_xml import render_test_alta,SF
    from xml.etree import ElementTree as ET
    settlement,series=setup_invoice(db_session,billing_env);issue(db_session,settlement,series)
    record=db_session.scalar(select(InvoiceFiscalRecord));root=ET.fromstring(render_test_alta(record.payload,record.hash))
    assert root.find('.//{'+SF+'}ImporteTotal').text=='367.84'
    assert root.find('.//{'+SF+'}CuotaTotal').text=='63.84'
    assert root.find('.//{'+SF+'}Huella').text==record.hash
    assert root.find('.//{'+SF+'}PrimerRegistro').text=='S'
    assert b'45.60' not in render_test_alta(record.payload,record.hash) # withholding is not a VAT quota
