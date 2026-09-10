import re
from uuid import uuid4
import pytest
from sqlalchemy import select, text
from backend.models.sepa_collection import SepaBatch, SepaExportArtifact
from tests.integration.api.test_sepa_collections import scenario, create, add_second_booking, PERIOD, COLLECTION


def immutable_snapshot(db, service):
    tables=['sepa_batch_groups','sepa_debits','sepa_debit_charge_allocations','sepa_export_artifacts','payments','payment_allocations']
    snapshot={t:db.execute(text('select * from '+t+' order by id')).all() for t in tables}
    columns=[c.name for c in SepaBatch.__table__.columns if c.name!='name']
    snapshot['batches']=db.execute(text('select '+','.join(columns)+' from sepa_batches order by id')).all()
    snapshot['files']={a.id:service.artifact_path(db,a.id).read_bytes() for a in db.scalars(select(SepaExportArtifact))}
    return snapshot


@pytest.mark.parametrize('state',['prepared','exported','presented','partial','collected','mixed_return','returned','cancelled'])
def test_rename_every_state_changes_only_name(client,db_session,scenario,state):
    service=scenario[0]
    ids=[c.id for c in scenario[4]]
    if state in ('partial','mixed_return'):
        _,charge=add_second_booking(db_session,scenario);ids.append(charge.id)
    batch=create(db_session,scenario,ids)
    assert batch.name is None and batch.display_name==f'Remesa {batch.id}'
    if state!='prepared':service.export(db_session,batch.id)
    if state not in ('prepared','exported','cancelled'):service.present(db_session,batch.id)
    debits=[d.id for g in service.get_batch(db_session,batch.id).groups for d in g.debits]
    if state in ('partial','collected','mixed_return','returned'):
        service.collect(db_session,batch.id,debits[:1] if state=='partial' else debits,COLLECTION)
    if state in ('mixed_return','returned'):service.return_debits(db_session,batch.id,debits[:1],COLLECTION)
    if state=='cancelled':service.cancel(db_session,batch.id,debits)
    before=immutable_snapshot(db_session,service)
    response=client.post(f'/collections/{batch.id}/rename',data={'name':'  Septiembre · Fincas ñ  ','reference':'NOT-ALLOWED','amount':'999'})
    assert response.status_code==200
    assert 'Septiembre · Fincas ñ' in response.text
    assert not re.search(r'>Remesas</a>',response.text)
    assert '>Nueva remesa</a>' in response.text and '>Cobros<' in response.text
    assert immutable_snapshot(db_session,service)==before
    assert db_session.get(SepaBatch,batch.id).name=='Septiembre · Fincas ñ'
    assert 'Septiembre · Fincas ñ' in client.get('/collections').text
    assert client.post(f'/collections/{batch.id}/rename',data={'name':'   '}).status_code==200
    assert db_session.get(SepaBatch,batch.id).name is None
    assert immutable_snapshot(db_session,service)==before


def test_name_validation_creation_and_privacy(client,db_session,scenario):
    service,booking,_,_,charges=scenario
    batch=service.create(db_session,PERIOD,[booking.room.property_id],COLLECTION,[c.id for c in charges],str(uuid4()),name=' Remesa privada ñ ')
    assert batch.name=='Remesa privada ñ'
    service.export(db_session,batch.id)
    artifact=db_session.scalar(select(SepaExportArtifact))
    assert 'Remesa privada ñ'.encode() not in service.artifact_path(db_session,artifact.id).read_bytes()
    for value in ('x'*161,'bad\nname'):
        response=client.post(f'/collections/{batch.id}/rename',data={'name':value})
        assert response.status_code==400 and response.headers['content-type'].startswith('text/html')
    assert db_session.get(SepaBatch,batch.id).name=='Remesa privada ñ'
    response=client.post(f'/collections/{batch.id}/rename',data={'name':'<script>prueba</script>'})
    assert '&lt;script&gt;prueba&lt;/script&gt;' in response.text
    assert '<script>prueba</script>' not in response.text
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as public:
        assert public.get(f'/collections/{batch.id}').status_code==404
        assert public.post(f'/collections/{batch.id}/rename',data={'name':'test'}).status_code==404


def test_create_ui_preserves_name_and_duplicate_names_allowed(client,db_session,scenario):
    service,booking,_,_,charges=scenario
    form={'name':'Mismo nombre','period':'2026-09','collection_date':str(COLLECTION),'property_ids':str(booking.room.property_id)}
    preview=client.post('/collections/preview',data=form)
    assert 'name="name" value="Mismo nombre"' in preview.text
    key=re.search(r'name="request_key" value="([^"]+)"',preview.text).group(1)
    form.update(request_key=key,charge_ids=[str(c.id) for c in charges])
    assert client.post('/collections/create',data=form).status_code==200
    _,charge=add_second_booking(db_session,scenario)
    batch=create(db_session,scenario,[charge.id])
    service.rename(db_session,batch.id,'Mismo nombre')
    assert len(db_session.scalars(select(SepaBatch).where(SepaBatch.name=='Mismo nombre')).all())==2


def test_inline_name_editor_render_and_accessibility(client,db_session,scenario):
    batch=create(db_session,scenario)
    page=client.get(f'/collections/{batch.id}')
    assert page.status_code==200
    assert '<summary>Editar remesa</summary>' not in page.text
    assert 'aria-label="Editar nombre de la remesa"' in page.text
    assert 'data-name-edit' in page.text
    assert '<form hidden id="batch-name-form"' in page.text
    assert f'action="/collections/{batch.id}/rename"' in page.text
    assert 'aria-label="Guardar nombre"' in page.text
    assert 'aria-label="Cancelar edición del nombre"' in page.text
    assert 'aria-describedby="batch-name-help"' in page.text
    css=client.get('/static/css/collection-name.css').text
    assert ':focus-within' in css and ':hover' in css
    assert '(hover: hover)' in css and '(pointer: fine)' in css
    assert '(min-width: 992px)' in css and 'min-width: 0' in css
    js=client.get('/static/js/collections.js').text
    assert "event.key === 'Escape'" in js and 'form.reset()' in js
    assert 'input.focus()' in js and 'edit.focus()' in js
