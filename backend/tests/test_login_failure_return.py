"""Offline failure/return-path regression, shared by Kakao and Naver.
All database/provider calls are explicit mocks; never use real account keys.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import re
from unittest.mock import Mock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from test_oauth import app, settings, ORIGIN
import auth_core as core
import auth_http as auth
import oauth_http as h
import oauth_store as store
import oauth_providers as providers


def browser():
    client = TestClient(app(), base_url=ORIGIN)
    client.cookies.set(h.BROWSER, 'B' * 43, domain='richon.example.invalid', path='/')
    return client


@pytest.mark.parametrize('provider', ['kakao', 'naver'])
@pytest.mark.parametrize('target', ['/', '/apply.html', '/portal/mypage'])
def test_login_start_preserves_return_on_store_failure(monkeypatch, provider, target):
    client = browser()
    response = client.get('/auth/login', params={'return_to': target})
    proof = re.search(r'name="csrf" value="([^"]+)"', response.text)[1]
    begin = Mock(side_effect=RuntimeError('SYNTHETIC_PRIVATE'))
    authorize = Mock()
    monkeypatch.setattr(store, 'begin', begin)
    monkeypatch.setattr(providers, 'authorization_url', authorize)
    response = client.post('/auth/start', data={'csrf': proof, 'provider': provider,
                            'return_to': target}, headers={'Origin': ORIGIN}, follow_redirects=False)
    assert response.status_code == 303
    expected = h.failed(target).headers['location']
    assert response.headers['location'] == expected
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert 'SYNTHETIC_PRIVATE' not in response.text + expected
    authorize.assert_not_called()


@pytest.mark.parametrize('provider', ['kakao', 'naver'])
@pytest.mark.parametrize('failure', ['cancel', 'provider-failure'])
def test_callback_retry_retains_server_resolved_return(monkeypatch, provider, failure):
    client = browser()
    monkeypatch.setattr(store, 'consume_attempt', Mock(return_value='/apply.html'))
    exchange = Mock(side_effect=providers.ProviderRejected())
    monkeypatch.setattr(providers, 'exchange', exchange)
    query = {'state': 'S' * 43}
    query.update({'error': 'access_denied'} if failure == 'cancel' else {'code': 'synthetic'})
    response = client.get('/auth/' + provider + '/callback', params=query, follow_redirects=False)
    assert response.headers['location'] == '/auth/login?error=login_failed&return_to=%2Fapply.html'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert auth.COOKIE not in response.headers.get('set-cookie', '')
    assert exchange.call_count == (0 if failure == 'cancel' else 1)


@pytest.mark.parametrize('provider', ['kakao', 'naver'])
@pytest.mark.parametrize('stage', ['registration', 'session'])
def test_signup_failure_retains_only_validated_ticket_return(monkeypatch, provider, stage):
    client = browser()
    client.cookies.set(h.TICKET, 'T' * 43, domain='richon.example.invalid', path='/')
    identity = core.VerifiedIdentity(provider, settings().providers[provider].identity_scope, 'mock', '가상 회원')
    monkeypatch.setattr(store, 'pending', Mock(return_value=(identity, '/apply.html')))
    register = Mock(side_effect=RuntimeError('PRIVATE') if stage == 'registration' else None,
                    return_value=uuid4())
    issue = Mock(side_effect=RuntimeError('PRIVATE'))
    monkeypatch.setattr(core, 'register_verified_identity', register)
    monkeypatch.setattr(core, 'issue_session', issue)
    data = {'csrf': h.proof('B' * 43, 'T' * 43), 'terms': 'yes', 'privacy': 'yes',
            'terms_version': settings().terms_version, 'privacy_version': settings().privacy_version}
    response = client.post('/auth/signup', data=data, headers={'Origin': ORIGIN}, follow_redirects=False)
    assert response.headers['location'] == '/auth/login?error=login_failed&return_to=%2Fapply.html'
    assert auth.COOKIE not in response.headers.get('set-cookie', '')
    assert 'PRIVATE' not in response.text
    assert issue.call_count == (0 if stage == 'registration' else 1)


def test_failed_ticket_lookup_cannot_choose_external_return(monkeypatch):
    client = browser()
    client.cookies.set(h.TICKET, 'T' * 43, domain='richon.example.invalid', path='/')
    monkeypatch.setattr(store, 'pending', Mock(side_effect=store.InvalidFlow()))
    register = Mock()
    monkeypatch.setattr(core, 'register_verified_identity', register)
    data = {'csrf': h.proof('B' * 43, 'T' * 43), 'terms': 'yes', 'privacy': 'yes',
            'terms_version': settings().terms_version, 'privacy_version': settings().privacy_version}
    response = client.post('/auth/signup', data=data, headers={'Origin': ORIGIN}, follow_redirects=False)
    assert response.headers['location'] == '/auth/login?error=login_failed'
    register.assert_not_called()


def test_complete_keeps_secure_cookie_on_return(monkeypatch):
    from starlette.requests import Request
    session = core.IssuedSession('A' * 43, datetime.now(timezone.utc) + timedelta(hours=1))
    monkeypatch.setattr(core, 'issue_session', Mock(return_value=session))
    request = Request({'type': 'http', 'headers': []})
    response = h.complete(uuid4(), request, '/apply.html')
    cookies = response.headers.getlist('set-cookie')
    assert response.headers['location'] == '/apply.html'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert len(cookies) == 3
    assert all('Secure' in x and 'HttpOnly' in x and 'SameSite=lax' in x and 'Path=/' in x for x in cookies)
    assert not any('Domain=' in x for x in cookies)
    assert 'A' * 43 not in response.headers['location']
