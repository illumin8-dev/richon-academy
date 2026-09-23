"""Login UX/security regressions. Mock store/providers; never a live DB/account."""
from unittest.mock import Mock
import hashlib
import re
import pytest
from fastapi.testclient import TestClient
from test_oauth import app, ORIGIN
import oauth_http as h
import oauth_providers as p
import oauth_store as store
from portal_entry import EdgeBoundary, allowed


def target(response):
    return re.search(r'name="return_to" value="([^"]+)"', response.text)[1]


def test_direct_login_defaults_home_and_uses_original_asset():
    c = TestClient(app(), base_url=ORIGIN)
    response = c.get('/auth/login')
    assert target(response) == '/'
    assert 'src="/auth/assets/kakao-login.png"' in response.text
    assert 'img-src \'self\'' in response.headers['content-security-policy']
    image = c.get('/auth/assets/kakao-login.png')
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    assert hashlib.sha256(image.content).hexdigest() == 'ed361544b384131f777d6085638182abc8483a6b95fe2fead12acb3b9425b04e'
    assert c.post('/auth/assets/kakao-login.png').status_code == 405


@pytest.mark.parametrize('path', sorted(p.RETURNS))
def test_allowlisted_return_paths_and_explicit_precedence(path):
    c = TestClient(app(), base_url=ORIGIN)
    assert target(c.get('/auth/login', params={'return_to': path}, headers={'Referer':ORIGIN+'/apply.html'})) == path
    assert target(c.get('/auth/login', headers={'Referer':ORIGIN+path+'?discard=secret#discard'})) == path


@pytest.mark.parametrize('value', ['https://evil.invalid','//evil.invalid','/auth/login','/auth/kakao/callback','/apply.html?code=x','/apply.html#x','/%2f%2fevil.invalid','/portal/../apply.html',''])
def test_invalid_explicit_target_fails_closed(value):
    c = TestClient(app(), base_url=ORIGIN)
    response = c.get('/auth/login', params={'return_to':value})
    assert response.status_code == 422 and response.json() == {'detail':'invalid_return'}
    assert response.headers['referrer-policy'] == 'no-referrer'


def test_duplicate_return_not_silently_selected():
    c = TestClient(app(), base_url=ORIGIN)
    assert c.get('/auth/login?return_to=/&return_to=/apply.html').status_code == 422


@pytest.mark.parametrize('value', ['https://evil.invalid/apply.html',ORIGIN+'.evil.invalid/apply.html',ORIGIN+'/auth/login','https://user:pass@richon.example.invalid/apply.html',ORIGIN+'/portal/../apply.html'])
def test_bad_referer_falls_back_home(value):
    assert target(TestClient(app(),base_url=ORIGIN).get('/auth/login',headers={'Referer':value})) == '/'


@pytest.mark.parametrize('origin', [None, 'null', 'https://evil.invalid'])
def test_origin_is_not_relaxed_even_with_valid_form_proof(monkeypatch, origin):
    c = TestClient(app(),base_url=ORIGIN)
    response = c.get('/auth/login')
    csrf = re.search(r'name="csrf" value="([^"]+)"',response.text)[1]
    begin = Mock();monkeypatch.setattr(store,'begin',begin)
    headers = {} if origin is None else {'Origin':origin}
    result = c.post('/auth/start',data={'csrf':csrf,'provider':'kakao'},headers=headers)
    assert result.status_code == 403 and result.json()['detail'] == 'csrf_failed'
    begin.assert_not_called()


def test_cross_site_metadata_still_rejected(monkeypatch):
    c = TestClient(app(),base_url=ORIGIN);response = c.get('/auth/login')
    csrf = re.search(r'name="csrf" value="([^"]+)"',response.text)[1]
    begin = Mock();monkeypatch.setattr(store,'begin',begin)
    result = c.post('/auth/start',data={'csrf':csrf,'provider':'kakao'},headers={'Origin':ORIGIN,'Sec-Fetch-Site':'cross-site'})
    assert result.status_code == 403;begin.assert_not_called()


def test_edge_middleware_only_relaxes_successful_form_document(monkeypatch):
    a=app();a.add_middleware(EdgeBoundary,enabled=True,secret='E'*43)
    c=TestClient(a,base_url=ORIGIN,headers={'X-Richon-Edge-Key':'E'*43})
    assert c.get('/auth/login').headers['referrer-policy']=='same-origin'
    invalid=c.get('/auth/login?return_to=//evil.invalid')
    assert invalid.status_code==422 and invalid.headers['referrer-policy']=='no-referrer'
    callback=c.get('/auth/kakao/callback?code=synthetic&state=bad',follow_redirects=False)
    assert callback.status_code==303 and callback.headers['referrer-policy']=='no-referrer'
    image=c.get('/auth/assets/kakao-login.png')
    assert image.status_code==200 and image.headers['referrer-policy']=='no-referrer'
    assert c.get('/auth/assets/kakao-login.png',headers={'X-Richon-Edge-Key':'wrong'}).status_code==403
    assert not allowed('/auth/assets/other.png','GET') and not allowed('/auth/assets/kakao-login.png','POST')


def test_cancel_preserves_allowlisted_return_and_no_referrer(monkeypatch):
    c=TestClient(app(),base_url=ORIGIN);c.get('/auth/login')
    monkeypatch.setattr(store,'consume_attempt',Mock(return_value='/apply.html'))
    exchange=Mock();monkeypatch.setattr(p,'exchange',exchange)
    r=c.get('/auth/kakao/callback?state='+('S'*43)+'&error=access_denied',follow_redirects=False)
    assert r.headers['location']=='/auth/login?error=login_failed&return_to=%2Fapply.html'
    assert r.headers['referrer-policy']=='no-referrer';exchange.assert_not_called()


def test_completion_never_issues_session_for_unapproved_destination(monkeypatch):
    issue=Mock();monkeypatch.setattr(h.core,'issue_session',issue)
    with pytest.raises(store.InvalidFlow):h.complete('unused',None,'https://evil.invalid')
    issue.assert_not_called()
