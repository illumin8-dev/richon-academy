"""Enrollment query/security contracts; no cloud access or real identities."""
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import ValidationError

import enrollments as api
from auth_core import Principal
from auth_http import require_member
from main import invalid_request


@pytest.mark.parametrize('value',[1,3,12,'1','3','12'])
def test_accepts_only_supported_month_plans(value):
    assert api.Filters(months=value).months in (1,3,12)


@pytest.mark.parametrize('bad',[0,2,6,30,True,1.0,'01','1.0','12 months'])
def test_rejects_other_plans(bad):
    with pytest.raises(ValidationError): api.Filters(months=bad)


@pytest.mark.parametrize('values',[
    {'limit':0},{'limit':51},{'offset':10001},{'q':'x'*201},
    {'q':'foo\nbar'},{'cohort':'\u200b'},{'member_id':str(uuid4())},
    {'sort':'full_name;DROP TABLE x'},{'end_from':'2026-10-10','end_to':'2026-10-01'},
    {'receipt':'issued'},{'status':'paid'},{'course_id':'../private'},
])
def test_invalid_filter_contract(values):
    with pytest.raises(ValidationError): api.Filters(**values)


def client_for(role,monkeypatch,handler=None):
    app=FastAPI();app.add_exception_handler(RequestValidationError,invalid_request)
    principal=Principal(uuid4(),'테스트',role,datetime.now(timezone.utc))
    app.dependency_overrides[require_member]=lambda:principal
    app.include_router(api.make_router())
    fake=Mock(return_value=handler)
    monkeypatch.setattr(api.store,'overview',fake)
    return TestClient(app),principal,fake


def empty_data():
    return dict(as_of='2026-10-01',items=[],courses=[],courses_truncated=False,
                summary=dict(enrollment_count=0,learner_count=0,active_learners=0,
                             scheduled_enrollments=0,ending_soon=0,pending_enrollments=0,needs_review=0),
                limit=20,offset=0,has_more=False)


def test_member_cannot_query_admin_even_with_query_identity(monkeypatch):
    client,_,fake=client_for('member',monkeypatch,empty_data())
    with client:
        assert client.get('/portal/api/admin/enrollments').status_code==403
    fake.assert_not_called()


def test_my_query_uses_only_session_identity(monkeypatch):
    client,principal,fake=client_for('member',monkeypatch,empty_data())
    with client:
        r=client.get('/portal/api/me/enrollments')
        assert r.status_code==200 and r.headers['cache-control']=='no-store'
        assert fake.call_args.kwargs['member_id']==principal.member_id
        assert client.get('/portal/api/me/enrollments',params={'member_id':str(uuid4())}).status_code==422


def test_admin_query_and_string_month_filter(monkeypatch):
    client,_,fake=client_for('admin',monkeypatch,empty_data())
    with client:
        assert client.get('/portal/api/admin/enrollments?months=3').status_code==200
        assert fake.call_args.args[0].months==3
        assert fake.call_args.kwargs['member_id'] is None


def test_anonymous_is_denied_before_store(monkeypatch):
    app=FastAPI();app.include_router(api.make_router());fake=Mock();monkeypatch.setattr(api.store,'overview',fake)
    with TestClient(app) as client:
        assert client.get('/portal/api/admin/enrollments').status_code==401
        assert client.get('/portal/api/me/enrollments').status_code==401
    fake.assert_not_called()


def test_db_failure_never_returns_empty_or_leaks(monkeypatch):
    client,_,fake=client_for('admin',monkeypatch)
    fake.side_effect=RuntimeError('secret-dsn synthetic@private.invalid')
    with client:
        r=client.get('/portal/api/admin/enrollments')
        assert r.status_code==503 and r.json()=={'detail':'enrollment_store_unavailable'}
        assert 'secret-dsn' not in r.text and 'private.invalid' not in r.text


def test_contract_failure_is_safe_503(monkeypatch):
    client,_,_=client_for('admin',monkeypatch,{'secret':'no-leak'})
    with client:
        r=client.get('/portal/api/admin/enrollments')
        assert r.status_code==503 and 'no-leak' not in r.text


def test_no_registration_or_renewal_http_write(monkeypatch):
    client,_,fake=client_for('admin',monkeypatch,empty_data())
    with client:
        for method in ('post','put','patch','delete'):
            assert getattr(client,method)('/portal/api/admin/enrollments').status_code==405
    fake.assert_not_called()


def test_default_off_and_partial_configuration_fails(monkeypatch):
    monkeypatch.delenv('RICHON_ENROLLMENTS_ENABLED',raising=False)
    app=FastAPI();assert api.install_if_enabled(app) is False
    assert not any('/enrollments' in getattr(r,'path','') for r in app.routes)
    monkeypatch.setenv('RICHON_ENROLLMENTS_ENABLED','true')
    monkeypatch.delenv('RICHON_PORTAL_ENABLED',raising=False)
    with pytest.raises(ValueError): api.install_if_enabled(app)
