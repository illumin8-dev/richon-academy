"""Contract and validation checks. No real customer data or external services."""
from datetime import datetime,timezone
from uuid import uuid4
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import auth_core,auth_http,manual_models as m,manual_portal,manual_store
from main import invalid_request
ORIGIN='https://richon.example.invalid'
TOKEN='A'*43

@pytest.mark.parametrize('bad',[
 {'months':True},{'months':'3'},{'months':4},{'months':0},{'months':-1},
 {'applied_on':'2026-02-30'},{'applied_on':''}, {'paid_amount_krw':1000},
 {'payment_state':'recorded'}, {'payment_state':'paid'},
 {'receipt_state':'recorded_issued'}, {'receipt_ref':'unexpected'},
 {'confirmed':True,'payment_state':'pending'},{'quoted_amount_krw':True},
 {'quoted_amount_krw':-1},{'quoted_amount_krw':100000001},{'member_id':str(uuid4())},
])
def test_invalid_term(bad):
    with pytest.raises(ValidationError):m.Term(**{'months':3,'applied_on':'2026-09-22',**bad})

@pytest.mark.parametrize('bad',[
 {'name':''},{'name':'\x00name'},{'phone':'not a phone'},{'email':'not-an-email'},
 {'role':'admin'},{'member_id':str(uuid4())},{'original_joined_on':'2026-13-01'}])
def test_invalid_profile(bad):
    with pytest.raises(ValidationError):m.Profile(**{'name':'가상',**bad})

def test_phone_normalization_and_minimal_profile():
    assert m.Profile(name=' 가상 ',phone='+82 10-0000-0000').phone=='01000000000'
    assert m.Profile(name='가상').email is None

def test_evidence_and_exclusive_identity():
    term={'months':3,'applied_on':'2026-09-22','confirmed':True,'payment_state':'recorded',
          'paid_amount_krw':0,'paid_on':'2026-09-20','payment_ref':'가상 면제 기록'}
    assert m.Term(**term).confirmed
    body={'request_id':str(uuid4()),'reason':'가상 명단','course_id':'test','term':term}
    with pytest.raises(ValidationError):m.Create(**body)
    with pytest.raises(ValidationError):m.Create(**body,profile={'name':'가상'},existing_learner_id=str(uuid4()),learner_version=1)
    assert m.Create(**body,profile={'name':'가상'}).profile.name=='가상'

@pytest.fixture
def app():
    a=FastAPI();a.add_exception_handler(RequestValidationError,invalid_request)
    a.include_router(manual_portal.make_router(auth_http.AuthSettings(frozenset({ORIGIN}))))
    return a

POST_PATHS=['search','read','create','profile','terms/add','terms/edit','archive','courses']

@pytest.mark.parametrize('path',POST_PATHS)
def test_unauthenticated_writes_do_not_access_store(app,monkeypatch,path):
    fn=Mock(side_effect=AssertionError('unauthenticated store'))
    monkeypatch.setattr(manual_store,'mutate',fn)
    r=TestClient(app).post('/portal/api/admin/manual/'+path,json={})
    assert r.status_code==401;fn.assert_not_called()

@pytest.mark.parametrize('path',POST_PATHS)
def test_non_admin_denied(app,monkeypatch,path):
    app.dependency_overrides[auth_http.require_member]=lambda:auth_core.Principal(uuid4(),'가상','member',datetime.now(timezone.utc))
    fn=Mock();monkeypatch.setattr(manual_store,'mutate',fn)
    r=TestClient(app).post('/portal/api/admin/manual/'+path,json={})
    assert r.status_code==403;fn.assert_not_called()

@pytest.fixture
def admin_client(app):
    app.dependency_overrides[auth_http.require_member]=lambda:auth_core.Principal(uuid4(),'가상 운영자','admin',datetime.now(timezone.utc))
    return TestClient(app,base_url=ORIGIN,headers={'Cookie':auth_http.COOKIE+'='+TOKEN,'Origin':ORIGIN,'X-CSRF-Token':auth_core.csrf_token(TOKEN)})

@pytest.mark.parametrize('headers',[{'Origin':'https://evil.example.invalid'},{'X-CSRF-Token':'wrong'},{'Cookie':''}])
def test_csrf_is_required_even_for_admin(admin_client,headers):
    r=admin_client.post('/portal/api/admin/manual/search',headers=headers,json={})
    assert r.status_code in (401,403)

def test_search_body_not_url_and_errors_do_not_leak(admin_client,monkeypatch,caplog):
    query=Mock(side_effect=RuntimeError('private-customer-secret-marker'))
    monkeypatch.setattr(manual_store,'search',query)
    r=admin_client.post('/portal/api/admin/manual/search',json={'q':'가상 닉네임'})
    assert r.status_code==503 and 'private-customer-secret-marker' not in r.text+caplog.text
    assert r.headers['cache-control']=='no-store'

def test_store_conflict_remains_conflict(admin_client,monkeypatch):
    monkeypatch.setattr(manual_store,'mutate',Mock(side_effect=manual_store.Rejected('stale_record')))
    r=admin_client.post('/portal/api/admin/manual/archive',json={'enrollment_id':str(uuid4()),'request_id':str(uuid4()),'version':1,'reason':'가상 변경','archived':True})
    assert r.status_code==409 and r.json()=={'detail':'stale_record'}

def test_routes_off_by_default(monkeypatch):
    monkeypatch.delenv('RICHON_MANUAL_ENABLED',raising=False)
    a=FastAPI();assert manual_portal.install_if_enabled(a) is False
    assert TestClient(a).get('/portal/manual').status_code==404
    assert TestClient(a).post('/portal/api/admin/manual/create',json={}).status_code==404

def test_cannot_enable_without_dependencies(monkeypatch):
    monkeypatch.setenv('RICHON_MANUAL_ENABLED','true')
    with pytest.raises(ValueError):manual_portal.install_if_enabled(FastAPI())
