"""Canonical learning API contracts. No real customer data or production services."""
from datetime import date, datetime, timezone
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
    a.include_router(portal.make_router(auth_http.AuthSettings(frozenset({ORIGIN})),calendar_enabled=True))
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


def test_calendar_event_is_freeform_and_uses_october_palette():
    base=dict(request_id=uuid4(),reason='가상 일정',event_date=date(2026,10,8),
              color_hex='#00B622',course_label='자유 과정')
    value=model.CalendarEventCreate(**base)
    assert value.course_label=='자유 과정' and value.content_text=='' and value.display_kind=='EVENT'
    with pytest.raises(ValidationError):
        model.CalendarEventCreate(**{**base,'color_hex':'#123456'})


def test_calendar_banner_requires_valid_end_date():
    base=dict(request_id=uuid4(),reason='가상 연휴',display_kind='BANNER',event_date=date(2026,9,23),
              color_hex='#FF5757',course_label='추석연휴')
    assert model.CalendarEventCreate(**base,end_date=date(2026,9,26)).end_date==date(2026,9,26)
    for invalid in (None,date(2026,9,22)):
        with pytest.raises(ValidationError):
            model.CalendarEventCreate(**base,end_date=invalid)


@pytest.mark.parametrize('path',[
    '/portal/api/me/courses','/portal/api/admin/learning/programs',
    '/portal/api/admin/learning/runs','/portal/api/admin/learning/enrollments',
    '/portal/api/admin/learning/targets','/portal/api/admin/learning/calendar'
])
def test_unauthenticated_reads_never_reach_store(app,monkeypatch,path):
    blocked=Mock(side_effect=AssertionError('must not query'))
    monkeypatch.setattr(portal.store,'programs',blocked)
    monkeypatch.setattr(portal.store,'runs',blocked)
    monkeypatch.setattr(portal.store,'enrollments',blocked)
    monkeypatch.setattr(portal.store,'targets',blocked)
    monkeypatch.setattr(portal.store,'my_courses',blocked)
    monkeypatch.setattr(portal.store,'admin_calendar',blocked)
    assert TestClient(app).get(path).status_code==401
    assert not any(x.called for x in [blocked]) 


@pytest.mark.parametrize('path',[
    'programs','programs/update','runs','runs/update','sessions',
    'calendar-events','calendar-events/update','enrollments','enrollments/cancel'
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


def test_course_admin_keeps_freeform_calendar_decoupled():
    html=(portal.STATIC/'courses.html').read_text()
    js=(portal.STATIC/'courses.js').read_text()
    assert '캘린더는 강의 / 기수 데이터와 별도로 자유롭게 관리합니다.' in html
    assert '일정 / 영상 / 자료는 중앙관리 캘린더에서 관리합니다.' not in html
    for forbidden in ('id="session-form"','id="session-run"','id="session-list"','id="session-save"'):
        assert forbidden not in html
    for forbidden in ("$('session-form')","$('session-run')",'loadSessions','resetSessionForm','isoLocal('):
        assert forbidden not in js
