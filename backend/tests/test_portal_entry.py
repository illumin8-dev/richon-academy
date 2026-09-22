"""Portal origin gate and private-route exclusion. Synthetic config only."""
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
import auth_core
import portal_entry as entry

SECRET='s'*43

@pytest.fixture
def enabled(monkeypatch):
    for key in ['RICHON_MONTHLY_ENABLED','RICHON_MANUAL_ENABLED','NAVER_CLIENT_ID','NAVER_CLIENT_SECRET']:
        monkeypatch.delenv(key,raising=False)
    for key,value in {
        'RICHON_EDGE_ENABLED':'true','RICHON_EDGE_SECRET':SECRET,
        'RICHON_AUTH_ENABLED':'true','RICHON_OAUTH_ENABLED':'true','RICHON_PORTAL_ENABLED':'true',
        'RICHON_OAUTH_ORIGIN':entry.ORIGIN,'RICHON_AUTH_ALLOWED_ORIGINS':entry.ORIGIN,
        'KAKAO_CLIENT_ID':'synthetic','KAKAO_CLIENT_SECRET':'synthetic',
        'RICHON_TERMS_VERSION':'test-v1','RICHON_PRIVACY_VERSION':'test-v1',
        'RICHON_TERMS_URL':entry.ORIGIN+'/terms.html','RICHON_PRIVACY_URL':entry.ORIGIN+'/privacy.html',
    }.items():monkeypatch.setenv(key,value)
    return entry.build_app()

def test_disabled_without_configuration(monkeypatch):
    monkeypatch.delenv('RICHON_EDGE_ENABLED',raising=False)
    assert TestClient(entry.build_app()).get('/auth/login').status_code==503

def test_no_private_or_debug_route_mounted(enabled):
    paths={r.path for r in enabled.routes}
    assert not any(p.startswith('/orders') or p.startswith('/health') for p in paths)
    assert '/docs' not in paths and '/openapi.json' not in paths
    assert '/auth/login' in paths and '/portal/mypage' in paths

@pytest.mark.parametrize('headers',[{}, {'X-Richon-Edge-Key':'wrong'}, [('X-Richon-Edge-Key',SECRET),('X-Richon-Edge-Key',SECRET)]])
def test_origin_gate_before_any_application_request(enabled,monkeypatch,headers):
    resolve=Mock();monkeypatch.setattr(auth_core,'resolve_session',resolve)
    with TestClient(enabled) as c:assert c.get('/auth/me',headers=headers).status_code==403
    resolve.assert_not_called()

def test_login_html_cookies_and_private_route_denial(enabled):
    with TestClient(enabled,base_url=entry.ORIGIN,headers={'X-Richon-Edge-Key':SECRET}) as c:
        response=c.get('/auth/login')
        assert response.status_code==200 and '카카오로 로그인' in response.text
        assert SECRET not in response.text and 'synthetic' not in response.text
        assert 'Domain=' not in response.headers['set-cookie']
        assert 'Secure' in response.headers['set-cookie'] and 'HttpOnly' in response.headers['set-cookie']
        for path in ['/health/db','/orders','/auth/fake-login','/auth/%6cogin','/portal//mypage']:
            assert c.get(path).status_code==404
        assert c.get('/portal/api/admin/summary').status_code==401

def test_gate_never_replaces_member_or_admin_auth(enabled,monkeypatch):
    from datetime import datetime,timezone,timedelta
    from uuid import uuid4
    user=auth_core.Principal(uuid4(),'가상 사용자','member',datetime.now(timezone.utc)+timedelta(hours=1))
    monkeypatch.setattr(auth_core,'resolve_session',Mock(return_value=user))
    with TestClient(enabled,base_url=entry.ORIGIN,headers={'X-Richon-Edge-Key':SECRET,'Cookie':'__Host-richon-session='+'a'*43}) as c:
        assert c.get('/auth/me').status_code==200
        assert c.get('/portal/api/admin/summary').status_code==403

def test_actual_browser_origin_is_required(enabled):
    with TestClient(enabled,base_url=entry.ORIGIN,headers={'X-Richon-Edge-Key':SECRET}) as c:
        assert c.post('/auth/start',data={'provider':'kakao'},headers={'Origin':'https://evil.invalid'}).status_code==403

def test_request_limits_before_handlers(enabled):
    with TestClient(enabled,headers={'X-Richon-Edge-Key':SECRET}) as c:
        assert c.post('/auth/start',content=b'x'*65537).status_code==413
        assert c.post('/auth/start',content='x',headers={'Content-Length':'70000'}).status_code==413
        assert c.get('/auth/login?q='+'x'*8200).status_code==414

def test_invalid_configuration_fails_closed(enabled,monkeypatch):
    monkeypatch.setenv('RICHON_OAUTH_ORIGIN','https://other.example.invalid')
    with pytest.raises(ValueError):entry.build_app()
    monkeypatch.setenv('RICHON_OAUTH_ORIGIN',entry.ORIGIN)
    monkeypatch.setenv('RICHON_EDGE_SECRET','short')
    with pytest.raises(ValueError):entry.build_app()
