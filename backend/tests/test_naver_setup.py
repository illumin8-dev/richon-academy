"""Naver configuration tests only; never contact NAVER or load real credentials."""
from urllib.parse import parse_qs, urlsplit
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import oauth_http as http
import oauth_providers as providers


@pytest.fixture
def configured_env(monkeypatch):
    # Set every provider input explicitly so no inherited real key can be used.
    values = {
        'KAKAO_CLIENT_ID': 'synthetic-kakao', 'KAKAO_CLIENT_SECRET': 'synthetic-secret',
        'KAKAO_APP_ID': '1585992', 'NAVER_CLIENT_ID': '', 'NAVER_CLIENT_SECRET': '',
        'RICHON_OAUTH_ORIGIN': 'https://richonacademy.com',
        'RICHON_AUTH_ALLOWED_ORIGINS': 'https://richonacademy.com',
        'RICHON_TERMS_VERSION': 'test-v1', 'RICHON_PRIVACY_VERSION': 'test-v1',
        'RICHON_TERMS_URL': 'https://richonacademy.com/terms.html',
        'RICHON_PRIVACY_URL': 'https://richonacademy.com/privacy.html',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_unconnected_naver_does_not_create_login_button(configured_env):
    cfg = providers.Settings.from_env()
    app = FastAPI(); app.include_router(http.make_router(cfg))
    response = TestClient(app).get('/auth/login')
    assert set(cfg.providers) == {'kakao'}
    assert 'name="provider" value="naver"' not in response.text
    assert 'synthetic-secret' not in response.text


@pytest.mark.parametrize('present', ['NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET'])
def test_half_configured_naver_fails_closed(configured_env, present):
    configured_env.setenv(present, 'synthetic-naver')
    with pytest.raises(ValueError, match='invalid_oauth_credentials'):
        providers.Settings.from_env()


def test_callback_remains_fixed_while_return_destinations_change(configured_env):
    configured_env.setenv('NAVER_CLIENT_ID', 'synthetic-naver')
    configured_env.setenv('NAVER_CLIENT_SECRET', 'synthetic-naver-secret')
    cfg = providers.Settings.from_env()
    assert set(cfg.providers) == {'kakao', 'naver'}
    url = providers.authorization_url(cfg, 'naver', 'S' * 43, 'B' * 43)
    parsed = urlsplit(url); query = parse_qs(parsed.query)
    assert parsed.netloc == 'nid.naver.com' and parsed.path == '/oauth2.0/authorize'
    assert query['redirect_uri'] == ['https://richonacademy.com/auth/naver/callback']
    assert query['state'] == ['S' * 43]
    assert 'client_secret' not in query and 'return_to' not in query
    assert {'/', '/apply.html', '/portal/mypage'} <= providers.RETURNS
