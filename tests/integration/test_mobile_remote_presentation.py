"""Presentation regression checks, using synthetic DB and signed test identity."""
import re
from datetime import date
from backend.models.booking import Booking
from html.parser import HTMLParser
from urllib.parse import urlsplit
import pytest
from fastapi.testclient import TestClient
from backend.app_factory import create_app
from backend.database.session import get_db
from backend.core.admin_security import AdminSecurityMiddleware
from backend.core.admin_read_policy import permits
from tests.integration.test_admin_remote_security import config,key,verifier,headers
from tests.integration.api.test_bookings_routes import create_room
from backend.models.person import Person
from backend.models.owner import Owner

class Controls(HTMLParser):
 def __init__(self):super().__init__();self.forms=[];self.links=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='form':self.forms.append(a)
  if tag=='a':self.links.append(a.get('href',''))

@pytest.fixture
def remote_app(db_session,config,key):
 create_room(db_session);db_session.add(Booking(room_id=1,origin='manual',check_in=date(2026,11,1),check_out=date(2026,12,1),price=450));db_session.add(Person(full_name='Synthetic person',phone='+34 600 000 001',email='person@example.invalid'));db_session.add(Owner(legal_name='Synthetic owner'));db_session.commit()
 app=create_app(False)
 for m in app.user_middleware:
  if m.cls is AdminSecurityMiddleware:m.kwargs.update(config=config,verifier=verifier(config,key))
 app.dependency_overrides[get_db]=lambda:db_session
 return app

@pytest.mark.parametrize('path',['/','/gantt/','/properties/','/rooms/property/1','/rooms/1','/persons','/persons/1','/owners','/owners/1','/expenses','/settlements','/bookings/1/finance'])
def test_remote_html_has_no_mutation_forms_or_forbidden_navigation(remote_app,key,path):
 with TestClient(remote_app,base_url='https://admin.example.test',client=('127.0.0.1',111),headers=headers(key)) as c:
  r=c.get(path);assert r.status_code==200,r.text
  parsed=Controls();parsed.feed(r.text)
  assert 'Modo consulta' in r.text
  assert all(f.get('method','get').lower()=='get' or f.get('action')=='/bookings/person-search' for f in parsed.forms)
  for form in parsed.forms:
   assert permits(form.get('method','get').upper(),urlsplit(form.get('action',path)).path)
  if path=='/persons':
   assert '>Buscar</button>' in r.text
   assert r.text.count('class="person-sort-link"')==2
  for link in parsed.links:
   if not link or link.startswith('#'):continue
   path=urlsplit(link).path
   if link.startswith('/') and not link.startswith('//'):assert permits('GET',path),link
  assert 'id="bookingForm"' not in r.text

def test_local_keeps_booking_editor_and_remote_search_is_authorized(remote_app,key):
 with TestClient(remote_app,base_url='http://127.0.0.1',client=('127.0.0.1',111)) as c:
  r=c.get('/rooms/1');assert 'id="bookingForm"' in r.text
 with TestClient(remote_app,base_url='https://admin.example.test',client=('127.0.0.1',111),headers=headers(key)) as c:
  r=c.get('/');token=re.search('name="rm-admin-csrf" content="([^"]+)"',r.text)[1]
  r=c.get('/persons',params={'q':'Synthetic'});assert r.status_code==200
  assert 'Synthetic person' in r.text
  assert c.post('/bookings/create',data={'room_id':1},headers={'X-RM-CSRF':token}).status_code==403


@pytest.mark.parametrize('template,expected',[
 ('dashboard.html', ['Situación operativa', 'Ocupación', 'Próximas entradas']),
 ('gantt.html', ['Reservas por habitación', '2×', '⛶ Ampliar']),
])
def test_mobile_templates_preserve_utf8(template,expected):
 from pathlib import Path
 text=(Path(__file__).resolve().parents[2]/'backend/templates/pages'/template).read_text(encoding='utf-8')
 assert all(value in text for value in expected)
