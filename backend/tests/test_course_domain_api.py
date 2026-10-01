"""Canonical learning API contracts. No real customer data or production services."""
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

import auth_core
import auth_http
import course_domain_models as model
import course_domain_portal as portal
import course_domain_store as store
from main import invalid_request

ORIGIN='https://richon.example.invalid'
TOKEN='A'*43


@pytest.fixture
def app(monkeypatch):
    a=FastAPI();a.add_exception_handler(RequestValidationError,invalid_request)
    a.include_router(auth_http.make_router(auth_http.AuthSettings(frozenset({ORIGIN}))))
    monkeypatch.setenv('RICHON_AUTH_ENABLED','true')
    monkeypatch.setenv('RICHON_PORTAL_ENABLED','true')
    # course_domain_portal.make_router is tested in isolation; portal install state
    # is represented by the actual admin route required by install_if_enabled tests.
    a.include_router(portal.make_router(auth_http.AuthSettings(frozenset({ORIGIN}))))
    return a


def principal(role='admin'):
    return auth_core.Principal(uuid4(),'가상',role,datetime.now(timezone.utc))


@pytest.mark.parametrize('body',[
    {'access_mode':'fixed_months','fixed_months':None},
    {'access_mode':'date_range','fixed_months':2},
    {'access_mode':'fixed_months','fixed_months':0},
])
def test_program_access_model_validation(body):
    base=dict(request_id=uuid4(),reason='가상 테스트',program_id='pre-richon',title='가상 강의')
    with pytest.raises(ValidationError): model.ProgramCreate(**base,**body)


def test_grant_requires_exactly_one_explicit_target():
    base=dict(request_id=uuid4(),reason='가상 지급',run_id=uuid4())
    with pytest.raises(ValidationError): model.EnrollmentGrant(**base)
    with pytest.raises(ValidationError): model.EnrollmentGrant(**base,member_id=uuid4(),learner_id=uuid4())
    assert model.EnrollmentGrant(**base,member_id=uuid4()).member_id is not None


@pytest.mark.parametrize('bad',['http://example.invalid/video','javascript:alert(1)'])
def test_session_links_are_https_only(bad):
    with pytest.raises(ValidationError):
        model.SessionCreate(request_id=uuid4(),reason='가상 회차',run_id=uuid4(),
            sequence_no=1,title='1회',starts_at=datetime.now(timezone.utc),video_url=bad)


def test_calendar_event_range_validation():
    base=dict(request_id=uuid4(),reason='가상 일정',event_type='BRIEFING',title='무료 브리핑',
              starts_at=datetime.now(timezone.utc))
    assert model.CalendarEventCreate(**base).is_public is True
    with pytest.raises(ValidationError):
        model.CalendarEventCreate(**base,ends_at=base['starts_at'])


@pytest.mark.parametrize('path',[
    '/portal/api/me/courses','/portal/api/admin/learning/programs',
    '/portal/api/admin/learning/runs','/portal/api/admin/learning/enrollments',
    '/portal/api/admin/learning/targets'
])
def test_unauthenticated_reads_never_reach_store(app,monkeypatch,path):
    blocked=Mock(side_effect=AssertionError('must not query'))
    monkeypatch.setattr(portal.store,'programs',blocked)
    monkeypatch.setattr(portal.store,'runs',blocked)
    monkeypatch.setattr(portal.store,'enrollments',blocked)
    monkeypatch.setattr(portal.store,'targets',blocked)
    monkeypatch.setattr(portal.store,'my_courses',blocked)
    assert TestClient(app).get(path).status_code==401
    assert not any(x.called for x in [blocked]) 


@pytest.mark.parametrize('path',[
    'programs','programs/update','runs','runs/update','sessions','enrollments','enrollments/cancel'
])
def test_non_admin_writes_never_reach_store(app,monkeypatch,path):
    app.dependency_overrides[auth_http.require_member]=lambda:principal('member')
    blocked=Mock(side_effect=AssertionError('must not write'));monkeypatch.setattr(store,'mutate',blocked)
    r=TestClient(app,base_url=ORIGIN).post('/portal/api/admin/learning/'+path,json={})
    assert r.status_code==403;blocked.assert_not_called()


def test_admin_write_requires_origin_and_csrf(app,monkeypatch):
    app.dependency_overrides[auth_http.require_member]=lambda:principal('admin')
    blocked=Mock(return_value={'program_id':'pre-richon','version':1});monkeypatch.setattr(store,'mutate',blocked)
    c=TestClient(app,base_url=ORIGIN,headers={'Cookie':auth_http.COOKIE+'='+TOKEN})
    body={'request_id':str(uuid4()),'reason':'가상 생성','program_id':'pre-richon','title':'Pre리치온','access_mode':'fixed_months','fixed_months':2}
    assert c.post('/portal/api/admin/learning/programs',json=body).status_code==403
    r=c.post('/portal/api/admin/learning/programs',headers={'Origin':ORIGIN,'X-CSRF-Token':auth_core.csrf_token(TOKEN)},json=body)
    assert r.status_code==200,r.text
    blocked.assert_called_once()


def test_default_off_and_dependency_gate(monkeypatch):
    monkeypatch.delenv('RICHON_COURSE_DOMAIN_ENABLED',raising=False)
    a=FastAPI();assert portal.install_if_enabled(a) is False
    assert TestClient(a).get('/portal/courses').status_code==404
    monkeypatch.setenv('RICHON_COURSE_DOMAIN_ENABLED','true')
    monkeypatch.setenv('RICHON_AUTH_ENABLED','true');monkeypatch.setenv('RICHON_PORTAL_ENABLED','true')
    with pytest.raises(ValueError):portal.install_if_enabled(FastAPI())


def test_static_assets_have_no_token_storage_or_html_injection():
    for name in ('courses.js','calendar.js'):
        js=(portal.STATIC/name).read_text()
        for forbidden in ('innerHTML','insertAdjacentHTML','document.cookie','localStorage.','sessionStorage.','eval('):
            assert forbidden not in js
        assert "textContent" in js or "replaceChildren" in js
    assert "credentials:'same-origin'" in (portal.STATIC/'courses.js').read_text()
    assert "credentials:'same-origin'" in (portal.STATIC/'calendar.js').read_text()


def test_course_admin_reserves_session_editing_for_central_calendar():
    html=(portal.STATIC/'courses.html').read_text()
    js=(portal.STATIC/'courses.js').read_text()
    assert '일정 / 영상 / 자료는 중앙관리 캘린더에서 관리합니다.' in html
    for forbidden in ('id="session-form"','id="session-run"','id="session-list"','id="session-save"'):
        assert forbidden not in html
    for forbidden in ("$('session-form')","$('session-run')",'loadSessions','resetSessionForm','isoLocal('):
        assert forbidden not in js


def test_public_calendar_route_is_login_free_only_when_enabled(monkeypatch):
    a=FastAPI();a.add_exception_handler(RequestValidationError,invalid_request)
    a.include_router(auth_http.make_router(auth_http.AuthSettings(frozenset({ORIGIN}))))
    fake={'items':[],'previous_exists':False,'next_exists':True}
    monkeypatch.setattr(portal.store,'public_calendar',Mock(return_value=fake))
    a.include_router(portal.make_router(auth_http.AuthSettings(frozenset({ORIGIN})),calendar_enabled=True))
    r=TestClient(a).get('/portal/api/public/calendar?month=2026-10')
    assert r.status_code==200 and r.json()['month']=='2026-10'
    assert r.json()['prev_month'] is None and r.json()['next_month']=='2026-11'
    assert r.headers['cache-control']=='public, max-age=0, s-maxage=60'


def test_calendar_routes_default_off_in_router_fixture(app):
    assert TestClient(app).get('/portal/api/public/calendar?month=2026-10').status_code==404
