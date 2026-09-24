"""Optional-consent request contract; no external account or live database."""
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
import auth_core as core
import auth_http as auth
import consultation_privacy as privacy
import member_profile
import portal_store
from test_portal import app_with_portal, ORIGIN

PATH = '/portal/api/me/consultation-consent/withdraw'
TOKEN = 'S' * 43


def activate(monkeypatch):
    for key, value in ((privacy.FLAG, 'true'), ('RICHON_TERMS_VERSION', member_profile.VERSION),
                       ('RICHON_PRIVACY_VERSION', member_profile.VERSION),
                       ('RICHON_AUTH_ENABLED', 'true'), ('RICHON_PORTAL_ENABLED', 'true'),
                       ('RICHON_AUTH_ALLOWED_ORIGINS', ORIGIN)):
        monkeypatch.setenv(key, value)


@pytest.fixture
def client(monkeypatch):
    activate(monkeypatch)
    app = app_with_portal(monkeypatch)
    principal = core.Principal(uuid4(), '합성 회원', 'member', datetime.now(timezone.utc))
    monkeypatch.setattr(core, 'resolve_session', Mock(return_value=principal))
    c = TestClient(app, base_url=ORIGIN)
    c.cookies.set(auth.COOKIE, TOKEN)
    return c


def headers():
    return {'Origin': ORIGIN, 'X-CSRF-Token': core.csrf_token(TOKEN)}


def test_disabled_does_not_mount_write_route(monkeypatch):
    monkeypatch.delenv(privacy.FLAG, raising=False)
    assert not privacy.enabled()
    app = app_with_portal(monkeypatch)
    assert PATH not in {r.path for r in app.routes}
    write = Mock(); monkeypatch.setattr(privacy, 'withdraw', write)
    assert TestClient(app).post(PATH, json={'confirm': True}).status_code == 404
    write.assert_not_called()


@pytest.mark.parametrize('key,value', [(privacy.FLAG, 'TRUE'), ('RICHON_TERMS_VERSION', 'internal-test-v1'),
                                      ('RICHON_PRIVACY_VERSION', 'internal-test-v1'),
                                      ('RICHON_AUTH_ENABLED', 'false'), ('RICHON_PORTAL_ENABLED', 'false')])
def test_fail_closed_configuration(monkeypatch, key, value):
    activate(monkeypatch); monkeypatch.setenv(key, value)
    with pytest.raises(ValueError): privacy.enabled()


def test_only_cookie_owner_is_forwarded_and_no_cache(client, monkeypatch):
    result = privacy.WithdrawalResult(consultation_consent=False)
    operation = Mock(return_value=result); monkeypatch.setattr(privacy, 'withdraw', operation)
    r = client.post(PATH, headers=headers(), json={'confirm': True})
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
    assert r.json() == {'consultation_consent': False, 'age_range': None, 'gender': None, 'withdrawn_at': None}
    operation.assert_called_once_with(TOKEN)
    assert TOKEN not in r.text


@pytest.mark.parametrize('body', [{}, {'confirm': False}, {'confirm': 'true'}, {'confirm': 1},
                                 {'confirm': True, 'member_id': 'another'}, {'confirm': True, 'role': 'admin'}])
def test_malformed_or_injected_body_never_writes(client, monkeypatch, body):
    operation = Mock(); monkeypatch.setattr(privacy, 'withdraw', operation)
    r = client.post(PATH, headers=headers(), json=body)
    assert r.status_code == 422 and r.json() == {'detail': 'invalid_request'}
    operation.assert_not_called()


@pytest.mark.parametrize('query', ['?member_id=other', '?confirm=true', '?role=admin'])
def test_query_is_not_an_authority(client, monkeypatch, query):
    operation = Mock(); monkeypatch.setattr(privacy, 'withdraw', operation)
    assert client.post(PATH + query, headers=headers(), json={'confirm': True}).status_code == 422
    operation.assert_not_called()


@pytest.mark.parametrize('case', ['no_origin', 'null_origin', 'external', 'no_csrf', 'wrong_csrf',
                                 'duplicate_origin', 'duplicate_csrf', 'cross_site'])
def test_csrf_not_weakened(client, monkeypatch, case):
    operation = Mock(); monkeypatch.setattr(privacy, 'withdraw', operation)
    h = headers()
    if case == 'no_origin': h.pop('Origin')
    elif case == 'null_origin': h['Origin'] = 'null'
    elif case == 'external': h['Origin'] = 'https://evil.example.invalid'
    elif case == 'no_csrf': h.pop('X-CSRF-Token')
    elif case == 'wrong_csrf': h['X-CSRF-Token'] = core.csrf_token('B'*43)
    elif case == 'cross_site': h['Sec-Fetch-Site'] = 'cross-site'
    elif case == 'duplicate_origin': h = list(h.items()) + [('Origin', ORIGIN)]
    elif case == 'duplicate_csrf': h = list(h.items()) + [('X-CSRF-Token', h['X-CSRF-Token'])]
    r = client.post(PATH, headers=h, json={'confirm': True})
    assert r.status_code == 403 and r.headers['cache-control'] == 'no-store'
    operation.assert_not_called()


@pytest.mark.parametrize('case', ['absent', 'duplicate', 'invalid', 'revoked'])
def test_authentication_required(client, monkeypatch, case):
    operation = Mock(); monkeypatch.setattr(privacy, 'withdraw', operation)
    client.cookies.clear(); h = headers()
    if case == 'duplicate': h['Cookie'] = f'{auth.COOKIE}={TOKEN}; {auth.COOKIE}={TOKEN}'
    elif case == 'invalid': h['Cookie'] = f'{auth.COOKIE}=invalid'
    elif case == 'revoked':
        client.cookies.set(auth.COOKIE, TOKEN)
        monkeypatch.setattr(core, 'resolve_session', Mock(side_effect=core.AuthenticationRequired()))
    assert client.post(PATH, headers=h, json={'confirm': True}).status_code == 401
    operation.assert_not_called()


@pytest.mark.parametrize('exception,status', [(core.AuthenticationRequired(), 401), (RuntimeError('secret-personal-marker'), 503)])
def test_late_revocation_and_database_failure_are_not_success(client, monkeypatch, caplog, exception, status):
    monkeypatch.setattr(privacy, 'withdraw', Mock(side_effect=exception))
    r = client.post(PATH, headers=headers(), json={'confirm': True})
    assert r.status_code == status and r.headers['cache-control'] == 'no-store'
    assert 'secret-personal-marker' not in r.text + caplog.text


def test_get_cannot_mutate(client, monkeypatch):
    operation = Mock(); monkeypatch.setattr(privacy, 'withdraw', operation)
    assert client.get(PATH).status_code == 405
    operation.assert_not_called()


def test_capability_explicit_and_legacy_response_unchanged(client, monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(portal_store, 'profile', Mock(return_value={
        'member_id': uuid4(), 'display_name': '가상', 'role': 'member', 'created_at': now,
        'providers': ['naver'], 'linked_order_count': 0}))
    assert client.get('/portal/api/me').json()['consultation_withdrawal_available'] is True
    monkeypatch.setenv(privacy.FLAG, 'false')
    assert 'consultation_withdrawal_available' not in client.get('/portal/api/me').json()


def test_internal_operation_also_refuses_disabled_flag(monkeypatch):
    monkeypatch.delenv(privacy.FLAG, raising=False)
    with pytest.raises(ValueError, match='disabled'): privacy.withdraw(TOKEN)
