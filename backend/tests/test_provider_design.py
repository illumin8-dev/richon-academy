"""Official button resource contracts; synthetic settings, no real providers/DB."""
from dataclasses import replace
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from struct import unpack
from unittest.mock import Mock
import re
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_oauth import settings, ORIGIN
import oauth_http as h
import oauth_store as store
from portal_entry import EdgeBoundary, allowed

ASSETS = {
    'kakao': ((896, 92), 'ed361544b384131f777d6085638182abc8483a6b95fe2fead12acb3b9425b04e'),
    'naver': ((1472, 192), '4d086f9c7f12e8b99589669042415db9de4fd31a28f5eac8721ebf893caaf06d'),
}
KEY = 'E' * 43


def client(names=('kakao', 'naver')):
    cfg = settings()
    cfg = replace(cfg, providers={name: cfg.providers[name] for name in names})
    app = FastAPI(); app.include_router(h.make_router(cfg))
    app.add_middleware(EdgeBoundary, enabled=True, secret=KEY)
    return TestClient(app, base_url=ORIGIN, headers={'X-Richon-Edge-Key': KEY})


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(); self.items = []
    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


@pytest.mark.parametrize('name', ASSETS)
def test_original_resources_are_exact_get_only_and_still_gated(name):
    c = client(); path = f'/auth/assets/{name}-login.png'
    response = c.get(path)
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert response.content.startswith(b'\x89PNG\r\n\x1a\n')
    assert unpack('>II', response.content[16:24]) == ASSETS[name][0]
    assert sha256(response.content).hexdigest() == ASSETS[name][1]
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert allowed(path, 'GET') and not allowed(path, 'POST')
    assert c.post(path).status_code == 404
    assert c.get(path, headers={'X-Richon-Edge-Key': 'wrong'}).status_code == 403
    assert c.get('/auth/assets/unknown.png').status_code == 404


@pytest.mark.parametrize('names', [('kakao',), ('naver',), ('kakao', 'naver')])
def test_only_configured_providers_get_original_image_submit_buttons(names):
    response = client(names).get('/auth/login?return_to=%2Fapply.html')
    assert response.status_code == 200
    tags = Tags(); tags.feed(response.text)
    buttons = [a for t, a in tags.items if t == 'button']
    images = [a for t, a in tags.items if t == 'img']
    forms = [a for t, a in tags.items if t == 'form']
    assert len(buttons) == len(images) == len(forms) == len(names)
    for name, button, image, form in zip(names, buttons, images, forms):
        assert button['type'] == 'submit' and button['aria-label'].endswith('로그인')
        assert button['class'] == f'provider-login {name}-login'
        assert image['src'] == f'/auth/assets/{name}-login.png'
        assert (int(image['width']), int(image['height'])) == ASSETS[name][0]
        assert image['referrerpolicy'] == 'no-referrer'
        assert form['method'] == 'post' and form['action'] == '/auth/start'
    assert not any(t == 'input' and a.get('type') == 'password' for t, a in tags.items)
    assert 'test-secret' not in response.text and 'test-naver' not in response.text
    assert 'img-src \'self\'' in response.headers['content-security-policy']
    assert response.headers['referrer-policy'] == 'same-origin'
    assert 'name="return_to" value="/apply.html"' in response.text


@pytest.mark.parametrize('name', ASSETS)
def test_official_buttons_keep_origin_and_browser_proof_checks(monkeypatch, name):
    c = client(); page = c.get('/auth/login')
    csrf = re.search(r'name="csrf" value="([a-f0-9]+)"', page.text)[1]
    begin = Mock(return_value='S' * 43); monkeypatch.setattr(store, 'begin', begin)
    data = {'provider': name, 'csrf': csrf, 'return_to': '/'}
    assert c.post('/auth/start', data=data, headers={'Origin': 'null'}).status_code == 403
    bad = c.post('/auth/start', data={**data, 'csrf': 'x'}, headers={'Origin': ORIGIN})
    assert bad.status_code == 403 and bad.json()['detail'] == 'invalid_login_flow'
    begin.assert_not_called()
    ok = c.post('/auth/start', data=data, headers={'Origin': ORIGIN}, follow_redirects=False)
    assert ok.status_code == 303
    assert ok.headers['location'].startswith('https://kauth.kakao.com/' if name == 'kakao' else 'https://nid.naver.com/')
    assert 'test-secret' not in ok.headers['location']


def test_image_allowlist_and_equal_button_geometry_are_declared():
    root = Path(__file__).resolve().parents[1]
    ignore = (root / 'Dockerfile.portal.dockerignore').read_text()
    for name in ASSETS:
        assert f'!backend/portal_static/{name}-login.png' in ignore.splitlines()
    assert '!backend/portal_static/*' not in ignore.splitlines()
    html = client().get('/auth/login').text
    assert '.provider-login{' in html and 'height:48px;min-height:48px' in html
    assert '.naver-login{background:#03a94d}' in html
    assert '.kakao-login{background:#fee500}' in html
    assert '.naver-login img{width:368px;height:48px}' in html
