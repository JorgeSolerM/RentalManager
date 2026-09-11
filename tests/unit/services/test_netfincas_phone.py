import pytest
from backend.services.netfincas_phone import phone_candidates

@pytest.mark.parametrize('row,field,value',[
 ({'MOVIL':'+39 333-1234567'},'MOVIL','+39 333-1234567'),
 ({'MOVIL':'','TEL':'+34 (647) 123-456'},'TEL','+34 (647) 123-456'),
 ({'TEL':'','FAX':'  +39  3331234567  '},'FAX','+39 3331234567'),
 ({'MOVIL':'+34647123456','TEL':'+34 647 123 456','FAX':'+34(647)123456'},'MOVIL','+34647123456'),
])
def test_unique_candidate_priority(row,field,value):
 r=phone_candidates(row);assert not r['review'];assert r['chosen']['field']==field and r['value']==value

@pytest.mark.parametrize('value',['not a phone','123','------','000000000','12+345678','+34 1234567890123456'])
def test_invalid_fax(value):
 r=phone_candidates({'FAX':value});assert r['value'] is None

def test_distinct_numbers_require_review():
 r=phone_candidates({'MOVIL':'+39 3331234567','TEL':'+34 647123456','FAX':'+34 647123456'})
 assert r['review'] and r['conflict'] and r['value'] is None and len(r['candidates'])==3

def test_invalid_mobile_not_silently_ignored():
 r=phone_candidates({'MOVIL':'ask first','TEL':'+39 3331234567'})
 assert r['review'] and r['value'] is None


def test_verified_mobile_binding_not_counted_twice():
 r=phone_candidates({'_phone_mobile_field':'FAX','FAX':'+39 3331234567','TEL':''})
 assert len(r['candidates'])==1 and r['value']=='+39 3331234567'
 assert r['chosen']['label'].startswith('Móvil') and r['chosen']['field']=='FAX'
 r=phone_candidates({'_phone_mobile_field':'FAX','FAX':'+39 3331234567','TEL':'+39 333 1234567'})
 assert r['chosen']['field']=='FAX' and not r['review']


def test_explicit_conflict_selection_validated():
 row={'MOVIL':'+39 3331234567','TEL':'+34 647123456','FAX':'not a phone'}
 assert phone_candidates(row,'TEL')['value']=='+34 647123456'
 assert not phone_candidates(row,'TEL')['review']
 for field in ('FAX','UNKNOWN'):
  with pytest.raises(ValueError):phone_candidates(row,field)


def test_source_adapter_marks_verified_mobile(monkeypatch,tmp_path):
 from backend.services import netfincas_source as module
 from types import SimpleNamespace
 monkeypatch.setattr(module,'COLUMNS',{'ALQ_INQUILINOS':'CODIGO TEL FAX'})
 monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stderr='',stdout='CODIGO 101\nTEL <null>\nFAX +39 3331234567\n'))
 snapshot=module.FirebirdSource(tmp_path/'copy.ib',tmp_path/'isql')._marked(tmp_path/'copy.ib',{})
 candidate=phone_candidates(snapshot.tables['ALQ_INQUILINOS'][0])
 assert candidate['chosen']['label'].startswith('Móvil')


@pytest.mark.parametrize('entity',['ALQ_INQUILINOS','ALQ_INQUILINOS_H','ALQ_PROPIETARIOS'])
@pytest.mark.parametrize('tel,mobile,conflict',[
 ('+34647123456',None,False),(None,'+393331234567',False),
 ('+39 3331234567','+393331234567',False),('+34647123456','+393331234567',True)])
def test_entity_mapping(entity,tel,mobile,conflict):
 r=phone_candidates(dict(_phone_entity=entity,TEL=tel,FAX=mobile))
 assert r['conflict']==conflict
 assert all(c['label']=='Móvil NetFincas' for c in r['mobile_candidates'])
 if conflict:assert r['value'] is None and phone_candidates(dict(_phone_entity=entity,TEL=tel,FAX=mobile),'FAX')['value']==mobile
 else:assert r['value']


@pytest.mark.parametrize('entity',['CONTACTOS','EMPRESA','PROVEEDORES'])
def test_real_fax_not_promoted_to_phone(entity):
 r=phone_candidates(dict(_phone_entity=entity,FAX='+34647123456'))
 assert r['value'] is None
 with pytest.raises(ValueError):phone_candidates(dict(_phone_entity=entity,FAX='+34647123456'),'FAX')
