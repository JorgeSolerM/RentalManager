import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from backend.public.map_locations import Address, LocationCache
from backend.services.geocoding_queries import diagnostics, variants

A = Address('Ejemplo', '10', 'Elche')


def hit(road='Calle Ejemplo', number='10', city='Elche', lat='38.25'):
    return {'lat':lat,'lon':'-0.70','address':{'road':road,'house_number':number,'city':city}}


@pytest.fixture
def geo(tmp_path, monkeypatch):
    monkeypatch.delenv('PUBLIC_GEOCODING_ALIASES',raising=False)
    cache=LocationCache(tmp_path/'locations.sqlite3');cache.initialize()
    now=[100000.0];sleeps=[]
    def sleep(n): sleeps.append(n);now[0]+=n
    def run(handler,address=A,manual=False):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return cache.resolve_progressive(address,client=client,clock=lambda:now[0],sleep=sleep,manual=manual)
    return cache,now,sleeps,run


def test_original_exact_reused_and_audited(geo):
    cache,now,sleeps,run=geo;calls=[]
    def respond(r):calls.append(r);return httpx.Response(200,json=[hit()])
    assert run(respond)=='verified'
    assert run(respond,manual=True)=='verified'
    assert len(calls)==1
    d=diagnostics(cache,A)
    assert d['attempts'][0]['label']=='original' and d['attempts'][0]['http_status']==200
    assert d['entry']['reason']=='exact_street_number_city'


def test_castellano_then_valenciano_same_number_city(geo):
    cache,now,sleeps,run=geo;calls=[]
    def respond(r):
        calls.append(dict(r.url.params))
        return httpx.Response(200,json=[hit('Carrer Ejemplo',city='Elx')] if r.url.params['city']=='Elx' else [])
    assert run(respond)=='verified'
    assert len(calls)==3 and sleeps==[16,16]
    assert diagnostics(cache,A)['attempts'][0]['label']=='valenciano'
    assert calls[0]['street']=='10 Ejemplo'


def test_documented_equivalence_only(geo,tmp_path,monkeypatch):
    cache,now,sleeps,run=geo
    file=tmp_path/'aliases.json'
    file.write_text(json.dumps([{'city':'Elche','original':'Sintética','translated':'Sintètica Nova','evidence':'Documento de prueba sintético, misma vía'}]))
    monkeypatch.setenv('PUBLIC_GEOCODING_ALIASES',str(file))
    a=Address('Sintética','10','Elche')
    def respond(r):return httpx.Response(200,json=[hit('Carrer Sintètica Nova',city='Elx')] if 'Nova' in r.url.params['street'] else [])
    assert run(respond,a)=='verified'
    assert diagnostics(cache,a)['attempts'][0]['label']=='equivalencia_documentada'


def test_gerona_girona_probe_is_not_proof(geo):
    cache,now,sleeps,run=geo;a=Address('Gerona','5','Elche')
    def respond(r):return httpx.Response(200,json=[hit('Carrer Girona','5','Elx')] if 'Girona' in r.url.params['street'] else [])
    assert run(respond,a)=='review'
    entry=diagnostics(cache,a)['entry']
    assert entry['reason']=='unverified_street_equivalence' and entry['latitude'] is None


@pytest.mark.parametrize('payload',[[hit(lat='38.25'),hit(lat='38.26')], [hit(number='11')], [hit(city='Madrid')]])
def test_ambiguity_wrong_number_or_city_not_accepted(geo,payload):
    cache,now,sleeps,run=geo;calls=[]
    def respond(r):calls.append(r);return httpx.Response(200,json=payload)
    assert run(respond)=='review'
    assert diagnostics(cache,A)['entry']['latitude'] is None
    if len(payload)>1:assert len(calls)==1


@pytest.mark.parametrize('status',[403,429,503])
def test_provider_error_shared_pause_manual_cannot_bypass(geo,status):
    cache,now,sleeps,run=geo;calls=[]
    def respond(r):calls.append(r);return httpx.Response(status)
    assert run(respond)=='error'
    assert run(respond,manual=True)=='paused'
    assert run(respond,Address('Otra','2','Elche'),manual=True)=='paused'
    assert len(calls)==1 and diagnostics(cache,A)['attempts'][0]['reason']==f'http_{status}'
    now[0]+=86401
    assert run(lambda r:httpx.Response(200,json=[hit()]))=='verified'


def test_cached_reviews_manual_daily_limit_and_maximum(geo):
    cache,now,sleeps,run=geo;calls=[]
    def respond(r):calls.append(r);return httpx.Response(200,json=[])
    assert run(respond)=='review'
    count=len(calls)
    assert run(respond,manual=True)=='cached' and len(calls)==count
    for _ in range(2):now[0]+=86500;assert run(respond,manual=True)=='review'
    now[0]+=86500
    assert run(respond,manual=True)=='cached' and len(calls)==count*3


def test_address_change_preserves_old_entry(geo):
    cache,now,sleeps,run=geo
    assert run(lambda r:httpx.Response(200,json=[hit()]))=='verified'
    assert diagnostics(cache,Address('Ejemplo','11','Elche'))['entry'] is None
    assert diagnostics(cache,A)['entry']['status']=='verified'


def test_legacy_verified_cache_no_query_or_schema_destruction(geo):
    cache,now,sleeps,run=geo
    with sqlite3.connect(cache.path) as db:db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?)',(A.key,'verified',38.25,-.70,'exact_street_number_city',1,1,0))
    assert run(lambda r:pytest.fail('No HTTP for verified entry'))=='verified'
    with sqlite3.connect(cache.path) as db: assert len(db.execute('pragma table_info(locations)').fetchall())==8


def test_legacy_review_tries_only_new_variants(geo):
    cache,now,sleeps,run=geo;calls=[]
    with sqlite3.connect(cache.path) as db:db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?)',(A.key,'review',None,None,'no_exact_street_number_city',1,1,0))
    def respond(r):calls.append(r.url.params['street']);return httpx.Response(200,json=[hit()])
    assert run(respond)=='verified' and calls==['10 Calle Ejemplo']


def test_concurrent_double_click_only_one_query(geo):
    cache,now,sleeps,run=geo;calls=[]
    def respond(r):calls.append(r);return httpx.Response(200,json=[hit()])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:run(respond),range(2)))
    assert all(r in ('verified','paused') for r in results) and len(calls)==1


def test_only_known_prefixes_and_city_equivalence():
    a=Address('Avenida Ejemplo','2','Elche')
    choices=variants(a)
    assert any(v.street=='Avinguda Ejemplo' and v.city=='Elx' for v,_,_ in choices)
    assert all(v.number=='2' for v,_,_ in choices)


def test_legacy_exhausted_error_keeps_limit(geo):
    cache,now,sleeps,run=geo
    with sqlite3.connect(cache.path) as db:db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?)',(A.key,'error',None,None,'timeout',1,3,2))
    assert run(lambda r:pytest.fail('Exhausted legacy entry must not query'),manual=True)=='exhausted'


def test_timeout_and_invalid_response_are_not_false_matches(geo):
    cache,now,sleeps,run=geo
    def timeout(r):raise httpx.ReadTimeout('synthetic',request=r)
    assert run(timeout)=='error'
    assert diagnostics(cache,A)['entry']['reason']=='timeout'
    now[0]+=86401
    assert run(lambda r:httpx.Response(200,json={'not':'a result list'}))=='error'
    assert diagnostics(cache,A)['entry']['reason']=='invalid_response'


def test_incomplete_address_never_queries(geo):
    cache,now,sleeps,run=geo;a=Address('Ejemplo','','Elche')
    assert run(lambda r:pytest.fail('Incomplete'),a)=='incomplete'
    assert diagnostics(cache,a)['entry']['reason']=='incomplete_address'


def test_exhausted_property_does_not_block_other_properties():
    from types import SimpleNamespace
    from backend.public.map_locations import refresh_locations
    props=[SimpleNamespace(id=i,street='Ejemplo',street_number=str(i),city='Elche') for i in (1,2)]
    db=SimpleNamespace(scalars=lambda query:SimpleNamespace(all=lambda:props))
    answers=iter(['exhausted','verified'])
    cache=SimpleNamespace(initialize=lambda:None,resolve_progressive=lambda *a,**kw:next(answers))
    assert refresh_locations(db,cache=cache,client=object())=={'verified':1,'review':0,'error':1}
