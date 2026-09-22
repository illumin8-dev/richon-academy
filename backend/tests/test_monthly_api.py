"""Run on the pinned repository with its existing auth/portal fixtures. NOT run in the handoff environment."""
from datetime import datetime,timezone
from unittest.mock import Mock
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
import auth_core as core
import auth_http as auth
import monthly_portal as monthly
import monthly_store as store
from test_portal import app_with_portal,ORIGIN

@pytest.fixture
def app(monkeypatch):
    app=app_with_portal(monkeypatch)
    monkeypatch.setenv('RICHON_MONTHLY_ENABLED','true');monkeypatch.setenv('RICHON_AUTH_ALLOWED_ORIGINS',ORIGIN)
    assert monthly.install_if_enabled(app)
    return app

def principal(role='admin'):return core.Principal(uuid4(),'가상',role,datetime.now(timezone.utc))

@pytest.mark.parametrize('body',[{'month':'2026-13'},{'limit':51},{'offset':-1},{'q':'bad\n'},
 {'role':'admin'},{'member_id':str(uuid4())},{'plan_months':True},{'plan_months':'3'},
 {'end_from':'2027-02','end_to':'2026-10'},{'payment_state':'paid'},{'receipt_state':'issued'}])
def test_invalid_or_injected_filters(body):
    with pytest.raises(ValidationError):monthly.Filters(**{'month':'2026-10',**body})

@pytest.mark.parametrize('role,code',[(None,401),('member',403)])
def test_all_data_paths_require_admin(app,monkeypatch,role,code):
    if role:app.dependency_overrides[auth.require_member]=lambda:principal(role)
    blocked=Mock(side_effect=AssertionError('must not query'));monkeypatch.setattr(monthly,'read',blocked)
    c=TestClient(app,base_url=ORIGIN)
    assert c.get('/portal/api/admin/enrollments/options').status_code==code
    assert c.post('/portal/api/admin/enrollments/search',json={'month':'2026-10'}).status_code==code
    assert c.get('/portal/api/admin/enrollments/'+str(uuid4())+'/terms').status_code==code
    blocked.assert_not_called()

@pytest.mark.parametrize('origin,token',[(None,None),(ORIGIN,None),('https://other.example.invalid','valid'),(ORIGIN,'invalid')])
def test_search_requires_csrf(app,monkeypatch,origin,token):
    app.dependency_overrides[auth.require_member]=lambda:principal()
    raw='A'*43;headers={'Cookie':auth.COOKIE+'='+raw}
    if origin:headers['Origin']=origin
    if token:headers['X-CSRF-Token']=core.csrf_token(raw) if token=='valid' else 'b'*64
    blocked=Mock();monkeypatch.setattr(monthly,'read',blocked)
    r=TestClient(app,base_url=ORIGIN).post('/portal/api/admin/enrollments/search',headers=headers,json={'month':'2026-10'})
    assert r.status_code==403;blocked.assert_not_called()

def test_default_off(monkeypatch):
    monkeypatch.delenv('RICHON_MONTHLY_ENABLED',raising=False)
    app=FastAPI();assert monthly.install_if_enabled(app) is False
    assert TestClient(app).get('/portal/enrollments').status_code==404
    monkeypatch.setenv('RICHON_MONTHLY_ENABLED','true')
    with pytest.raises(ValueError):monthly.install_if_enabled(FastAPI())

def test_failure_not_empty_success(app,monkeypatch,caplog):
    app.dependency_overrides[auth.require_member]=lambda:principal()
    monkeypatch.setattr(store,'options',Mock(side_effect=RuntimeError('secret-marker')))
    r=TestClient(app).get('/portal/api/admin/enrollments/options')
    assert r.status_code==503 and r.json()=={'detail':'monthly_store_unavailable'}
    assert 'secret-marker' not in caplog.text+r.text
    assert r.headers['cache-control']=='no-store'

def test_shell_allowlist_and_browser_storage(app):
    c=TestClient(app);r=c.get('/portal/enrollments')
    assert r.status_code==200 and 'frame-ancestors' in r.headers['content-security-policy']
    for name in ['.env','monthly_store.py','004_monthly_enrollments.sql']:
        assert c.get('/portal/monthly-assets/'+name).status_code==404
    text=(monthly.STATIC/'enrollments.js').read_text()
    for forbidden in ['innerHTML','insertAdjacentHTML','document.cookie','localStorage.','sessionStorage.','eval(']:
        assert forbidden not in text
