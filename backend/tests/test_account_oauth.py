"""Account-action OAuth callback contracts with synthetic identities only."""
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import account_store as accounts
import auth_core as core
import auth_http as auth
import oauth_http as http
import oauth_providers as providers
from test_member_profile import cfg
from test_oauth import ORIGIN

BROWSER='B'*43
STATE='S'*43


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('RICHON_ACCOUNT_ENABLED','true')
    app=FastAPI();app.include_router(http.make_router(cfg()))
    c=TestClient(app,base_url=ORIGIN)
    c.cookies.set(http.BROWSER,BROWSER)
    return c


def verified(provider='kakao',subject='42'):
    settings=cfg()
    identity=core.VerifiedIdentity(provider,settings.providers[provider].identity_scope,subject,'회원')
    return providers.VerifiedProviderSession(identity,'synthetic-access-token')


def callback(client,provider='kakao'):
    return client.get(f'/auth/{provider}/callback',params={'state':STATE,'code':'synthetic-code'},follow_redirects=False)


def test_link_callback_stages_separate_confirmation_without_provider_unlink(client,monkeypatch):
    mid=uuid4()
    attempt=accounts.AccountAttempt(mid,'link','kakao',cfg().providers['kakao'].identity_scope)
    monkeypatch.setattr(accounts,'consume_action_attempt',Mock(return_value=attempt))
    session=verified()
    monkeypatch.setattr(providers,'exchange_session',Mock(return_value=session))
    monkeypatch.setattr(accounts,'finish_verified_action',Mock(return_value=('link',mid,'L'*43)))
    unlink=Mock(side_effect=AssertionError('link must not unlink provider'));monkeypatch.setattr(providers,'unlink_access',unlink)
    response=callback(client)
    assert response.status_code==303 and response.headers['location']=='/portal/mypage'
    assert '__Host-richon-link=' in response.headers['set-cookie']
    unlink.assert_not_called()


def test_unlink_callback_revokes_provider_before_local_identity_and_rotates_session(client,monkeypatch):
    mid=uuid4();attempt=accounts.AccountAttempt(mid,'unlink','kakao',cfg().providers['kakao'].identity_scope)
    monkeypatch.setattr(accounts,'consume_action_attempt',Mock(return_value=attempt))
    session=verified();monkeypatch.setattr(providers,'exchange_session',Mock(return_value=session))
    monkeypatch.setattr(accounts,'finish_verified_action',Mock(return_value=('unlink',mid,None)))
    order=[]
    monkeypatch.setattr(providers,'unlink_access',lambda settings,value:order.append('provider'))
    monkeypatch.setattr(accounts,'complete_unlink',lambda settings,member,identity:(order.append('local') or ['naver']))
    issued=core.IssuedSession('Y'*43,datetime.now(timezone.utc))
    monkeypatch.setattr(core,'issue_session',Mock(return_value=issued))
    response=callback(client)
    assert response.status_code==303 and response.headers['location']=='/portal/mypage'
    assert order==['provider','local']
    assert auth.COOKIE in response.headers.get('set-cookie','')


def test_provider_unlink_failure_is_tracked_and_local_identity_is_kept(client,monkeypatch):
    mid=uuid4();attempt=accounts.AccountAttempt(mid,'unlink','kakao',cfg().providers['kakao'].identity_scope)
    monkeypatch.setattr(accounts,'consume_action_attempt',Mock(return_value=attempt))
    monkeypatch.setattr(providers,'exchange_session',Mock(return_value=verified()))
    monkeypatch.setattr(accounts,'finish_verified_action',Mock(return_value=('unlink',mid,None)))
    monkeypatch.setattr(providers,'unlink_access',Mock(side_effect=providers.ProviderRejected()))
    record=Mock();complete=Mock()
    monkeypatch.setattr(accounts,'record_unlink_failure',record)
    monkeypatch.setattr(accounts,'complete_unlink',complete)
    response=callback(client)
    assert response.status_code==303 and response.headers['location']=='/portal/mypage'
    record.assert_called_once_with(mid,'kakao');complete.assert_not_called()


@pytest.mark.parametrize('remaining,target',[(['naver'],'/portal/mypage'),([], '/')])
def test_withdraw_callback_unlinks_provider_then_finalizes_only_after_last_identity(client,monkeypatch,remaining,target):
    mid=uuid4();attempt=accounts.AccountAttempt(mid,'withdraw','kakao',cfg().providers['kakao'].identity_scope)
    monkeypatch.setattr(accounts,'consume_action_attempt',Mock(return_value=attempt))
    monkeypatch.setattr(providers,'exchange_session',Mock(return_value=verified()))
    monkeypatch.setattr(accounts,'finish_verified_action',Mock(return_value=('withdraw',mid,None)))
    unlink=Mock();monkeypatch.setattr(providers,'unlink_access',unlink)
    complete=Mock(return_value=remaining);monkeypatch.setattr(accounts,'complete_withdraw_provider',complete)
    finalize=Mock(return_value=0);monkeypatch.setattr(accounts,'finalize_withdrawal',finalize)
    response=callback(client)
    assert response.status_code==303 and response.headers['location']==target
    unlink.assert_called_once();complete.assert_called_once()
    if remaining: finalize.assert_not_called()
    else: finalize.assert_called_once_with(mid)


def test_account_callback_cancel_consumes_attempt_without_exchange(client,monkeypatch):
    mid=uuid4();attempt=accounts.AccountAttempt(mid,'unlink','kakao',cfg().providers['kakao'].identity_scope)
    consume=Mock(return_value=attempt);monkeypatch.setattr(accounts,'consume_action_attempt',consume)
    exchange=Mock(side_effect=AssertionError('cancel must not exchange code'));monkeypatch.setattr(providers,'exchange_session',exchange)
    response=client.get('/auth/kakao/callback',params={'state':STATE,'error':'access_denied'},follow_redirects=False)
    assert response.status_code==303 and response.headers['location']=='/portal/mypage'
    consume.assert_called_once();exchange.assert_not_called()
