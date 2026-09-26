"""Own-account HTTP contracts with synthetic identities only."""
from datetime import datetime,timezone
from unittest.mock import Mock
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import account_http as h
import account_store as store
import auth_core as core
import auth_http as auth
import oauth_http as oauth
from test_member_profile import cfg
from test_oauth import ORIGIN

TOKEN='X'*43


@pytest.fixture
def member():
    return core.Principal(uuid4(),'합성 회원','member',datetime.now(timezone.utc))


@pytest.fixture
def client(member):
    app=FastAPI();app.include_router(h.make_router(cfg()))
    app.dependency_overrides[auth.require_member]=lambda:member
    return TestClient(app,base_url=ORIGIN,headers={'Cookie':f'{auth.COOKIE}={TOKEN}'})


def headers():
    return {'Origin':ORIGIN,'X-CSRF-Token':core.csrf_token(TOKEN)}


def test_profile_update_uses_validated_values_and_csrf(client,member,monkeypatch):
    update=Mock();monkeypatch.setattr(store,'update_profile',update)
    body={'name':' 테스트 이름 ','phone':'010-1234-5678','email':'Tester@EXAMPLE.invalid',
          'age_range':'30-39','gender':'female','consultation_consent':True}
    assert client.post('/portal/api/me/profile',json=body).status_code==403
    response=client.post('/portal/api/me/profile',json=body,headers=headers())
    assert response.status_code==204
    saved=update.call_args.args[1]
    assert saved.name=='테스트 이름' and saved.phone=='01012345678' and saved.email=='Tester@example.invalid'
    assert saved.age_range=='30-39' and saved.gender=='female'


def test_marketing_consent_is_separate_optional_csrf_action(client,member,monkeypatch):
    update=Mock();monkeypatch.setattr(store,'set_marketing_consent',update)
    monkeypatch.setenv('RICHON_MARKETING_CONSENT_ENABLED','true')
    assert client.post('/portal/api/me/marketing',json={'consent':True}).status_code==403
    response=client.post('/portal/api/me/marketing',json={'consent':True},headers=headers())
    assert response.status_code==200
    assert response.json()=={'consent':True,'channels':['email','sms']}
    update.assert_called_once_with(member.member_id,True)


def test_marketing_consent_route_is_hidden_until_feature_enabled(client,member,monkeypatch):
    update=Mock();monkeypatch.setattr(store,'set_marketing_consent',update)
    monkeypatch.delenv('RICHON_MARKETING_CONSENT_ENABLED',raising=False)
    response=client.post('/portal/api/me/marketing',json={'consent':False},headers=headers())
    assert response.status_code==404
    update.assert_not_called()


def test_security_reports_freshness_and_safe_provider_failure_only(client,member,monkeypatch):
    monkeypatch.setattr(store,'recent_session',Mock(return_value=True))
    monkeypatch.setattr(store,'unlink_failure_pending',Mock(return_value=True))
    response=client.get('/portal/api/me/security')
    assert response.status_code==200
    assert response.json()=={'fresh_auth':True,'provider_unlink_failed':True}


def test_link_and_unlink_start_require_recent_existing_session(client,member,monkeypatch):
    monkeypatch.setattr(store,'recent_session',Mock(return_value=False))
    begin=Mock(return_value='S'*43);monkeypatch.setattr(store,'begin_action',begin)
    form={'csrf':core.csrf_token(TOKEN),'provider':'naver'}
    for path in ('/portal/api/me/logins/link/start','/portal/api/me/logins/unlink/start'):
        response=client.post(path,data=form,headers={'Origin':ORIGIN},follow_redirects=False)
        assert response.status_code==409
    begin.assert_not_called()


def test_reauth_start_allows_stale_session_and_uses_exact_linked_provider_flow(client,member,monkeypatch):
    monkeypatch.setattr(store,'recent_session',Mock(return_value=False))
    begin=Mock(return_value='S'*43);monkeypatch.setattr(store,'begin_action',begin)
    form={'csrf':core.csrf_token(TOKEN),'provider':'naver'}
    response=client.post('/portal/api/me/reauth/start',data=form,headers={'Origin':ORIGIN},follow_redirects=False)
    assert response.status_code==303 and response.headers['location'].startswith('https://nid.naver.com/')
    assert begin.call_args.args[3]=='reauth'
    assert '__Host-richon-oauth=' in response.headers['set-cookie']


def test_withdraw_prepare_requires_recent_auth_exact_phrase_then_tracks_status(client,member,monkeypatch):
    monkeypatch.setattr(store,'recent_session',Mock(return_value=True))
    prepare=Mock();monkeypatch.setattr(store,'prepare_withdrawal',prepare)
    status=Mock(return_value=['kakao','naver']);monkeypatch.setattr(store,'withdrawal_status',status)
    assert client.post('/portal/api/me/withdraw/prepare',json={'confirm':'탈퇴'},headers=headers()).status_code==422
    response=client.post('/portal/api/me/withdraw/prepare',json={'confirm':'회원탈퇴'},headers=headers())
    assert response.status_code==200 and response.json()=={'providers':['kakao','naver']}
    prepare.assert_called_once_with(member.member_id)
    assert client.get('/portal/api/me/withdraw/status').json()=={'providers':['kakao','naver']}


def test_withdraw_provider_start_requires_prepared_store_action_not_client_identity(client,member,monkeypatch):
    begin=Mock(return_value='S'*43);monkeypatch.setattr(store,'begin_action',begin)
    form={'csrf':core.csrf_token(TOKEN),'provider':'kakao'}
    response=client.post('/portal/api/me/withdraw/provider/start',data=form,headers={'Origin':ORIGIN},follow_redirects=False)
    assert response.status_code==303 and response.headers['location'].startswith('https://kauth.kakao.com/')
    assert begin.call_args.args[1:4]==(member.member_id,'kakao','withdraw')


def test_withdraw_cancel_is_csrf_protected(client,member,monkeypatch):
    cancel=Mock();monkeypatch.setattr(store,'cancel_withdrawal',cancel)
    assert client.post('/portal/api/me/withdraw/cancel').status_code==403
    assert client.post('/portal/api/me/withdraw/cancel',headers=headers()).status_code==204
    cancel.assert_called_once_with(member.member_id)


def test_link_confirmation_is_separate_from_provider_auth(client,member,monkeypatch):
    monkeypatch.setattr(store,'pending_link',Mock(return_value='kakao'))
    cookie=f"{auth.COOKIE}={TOKEN}; {oauth.LINK}={'L'*43}; {oauth.BROWSER}={'B'*43}"
    response=client.get('/portal/api/me/logins/link/pending',headers={'Cookie':cookie})
    assert response.status_code==200 and response.json()=={'provider':'kakao'}
    confirm=Mock(return_value=['kakao','naver']);monkeypatch.setattr(store,'confirm_link',confirm)
    response=client.post('/portal/api/me/logins/link/confirm',headers={**headers(),'Cookie':cookie})
    assert response.status_code==200 and response.json()=={'providers':['kakao','naver']}
    assert confirm.call_args.args[-1]==member.member_id


def test_fixed_store_errors_do_not_echo_private_values(client,member,monkeypatch):
    monkeypatch.setattr(store,'recent_session',Mock(return_value=True))
    monkeypatch.setattr(store,'prepare_withdrawal',Mock(side_effect=store.LifecycleNotReady()))
    response=client.post('/portal/api/me/withdraw/prepare',json={'confirm':'회원탈퇴'},headers=headers())
    assert response.status_code==503 and response.json()=={'detail':'withdrawal_cleanup_not_ready'}
    assert 'member_id' not in response.text
