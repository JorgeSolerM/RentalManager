import httpx
import pytest
from backend.cli.operational_status import release_manifest, verify_manifest, probe_services


def test_independent_manifest_detects_modified_or_missing_component(tmp_path):
    a=tmp_path/'admin.py';a.write_text('admin')
    b=tmp_path/'public.py';b.write_text('public')
    admin=release_manifest('admin','a'*40,{'backend/app_factory.py':a})
    public=release_manifest('public','b'*40,{'backend/app_factory.py':b})
    assert verify_manifest(admin)['matches'] and verify_manifest(public)['matches']
    a.write_text('new admin')
    assert not verify_manifest(admin)['matches'] and verify_manifest(public)['matches']
    b.unlink();assert not verify_manifest(public)['matches']
    with pytest.raises(ValueError):release_manifest('public','b'*40,{'backend/.env':a})


def test_probe_fixed_destinations_no_body_logging():
    calls=[]
    def respond(request):
        calls.append(str(request.url))
        if request.url.scheme=='https':raise httpx.ReadTimeout('secret',request=request)
        return httpx.Response(200,text='PRIVATE page contents')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:result=probe_services(client)
    assert len(calls)==6
    assert result['checks']['public_https']=={'error':'timeout'}
    assert 'PRIVATE' not in str(result) and 'secret' not in str(result)
