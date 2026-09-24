"""Shared account UI contract; no production accounts, tokens or database."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import oauth_http as oauth
import oauth_store
import portal
from portal_entry import EdgeBoundary
from test_oauth import settings, ORIGIN
from test_portal import app_with_portal
import member_profile

ROOT=Path(__file__).resolve().parents[2]
KEY='E'*43


def client(collect=False, names=('kakao','naver')):
    cfg=settings()
    cfg=replace(cfg,providers={name:cfg.providers[name] for name in names},
                terms_url=ORIGIN+'/terms.html',privacy_url=ORIGIN+'/privacy.html')
    if collect: cfg=replace(cfg,terms_version=member_profile.VERSION,privacy_version=member_profile.VERSION)
    app=FastAPI();app.include_router(oauth.make_router(cfg))
    app.add_middleware(EdgeBoundary,enabled=True,secret=KEY)
    return TestClient(app,base_url=ORIGIN,headers={'X-Richon-Edge-Key':KEY})


@pytest.mark.parametrize('collect',[False,True])
@pytest.mark.parametrize('names',[('kakao',),('naver',),('kakao','naver')])
def test_modal_bootstrap_is_bounded_and_browser_bound(monkeypatch,collect,names):
    begin=Mock();monkeypatch.setattr(oauth_store,'begin',begin)
    c=client(collect,names);r=c.get('/auth/login?view=modal&return_to=%2Fapply.html')
    assert r.status_code==200 and r.headers['content-type'].startswith('application/json')
    assert r.headers['cache-control']=='no-store' and r.headers['referrer-policy']=='no-referrer'
    data=r.json();assert set(data)=={'csrf','return_to','providers','collect_profile','notice'}
    assert data['providers']==list(names) and data['return_to']=='/apply.html'
    assert data['collect_profile'] is collect
    assert (data['notice'] is not None) is collect
    assert data['csrf']==oauth.proof(c.cookies.get(oauth.BROWSER))
    assert c.cookies.get(oauth.BROWSER) not in r.text
    for secret in ('test-secret','test-kakao','member_id','access_token'):
        assert secret not in r.text
    assert 'Secure' in r.headers['set-cookie'] and 'HttpOnly' in r.headers['set-cookie']
    assert c.get('/auth/login?view=modal&return_to=%2Fapply.html').json()==data
    begin.assert_not_called()


@pytest.mark.parametrize('query',['view=bad','view=modal&view=modal','view=modal&return_to=https://evil.invalid',
                                  'view=modal&return_to=/apply.html?course=pre','view=modal&return_to=/&return_to=/apply.html'])
def test_modal_query_cannot_expand_server_redirects(query):
    r=client().get('/auth/login?'+query)
    assert r.status_code==422 and r.headers['cache-control']=='no-store'


@pytest.mark.parametrize('origin',[None,'null','https://evil.invalid'])
def test_modal_does_not_weaken_origin(monkeypatch,origin):
    c=client();data=c.get('/auth/login?view=modal').json()
    begin=Mock();monkeypatch.setattr(oauth_store,'begin',begin)
    r=c.post('/auth/start',data={'csrf':data['csrf'],'provider':'kakao','return_to':'/'},headers={} if origin is None else {'Origin':origin})
    assert r.status_code==403;begin.assert_not_called()


@pytest.mark.parametrize('collect',[False,True])
def test_native_modal_confirmation_retains_existing_auth_contract(monkeypatch,collect):
    c=client(collect);data=c.get('/auth/login?view=modal').json()
    begin=Mock(return_value='S'*43);monkeypatch.setattr(oauth_store,'begin',begin)
    body={'csrf':data['csrf'],'provider':'naver','return_to':'/'}
    if collect:
        assert c.post('/auth/start',data=body,headers={'Origin':ORIGIN}).status_code==422
        begin.assert_not_called();body['over14']='yes'
    r=c.post('/auth/start',data=body,headers={'Origin':ORIGIN},follow_redirects=False)
    assert r.status_code==303 and r.headers['location'].startswith('https://nid.naver.com/')
    assert r.headers['referrer-policy']=='no-referrer';begin.assert_called_once()


def test_standalone_fallback_and_member_page_share_markup(monkeypatch):
    app=app_with_portal(monkeypatch);app.add_middleware(EdgeBoundary,enabled=True,secret=KEY)
    c=TestClient(app,base_url=ORIGIN,headers={'X-Richon-Edge-Key':KEY})
    page=c.get('/portal/mypage')
    assert page.headers['referrer-policy']=='same-origin'
    assert c.get('/portal/admin').headers['referrer-policy']=='no-referrer'
    assert c.get('/portal/api/me').headers['referrer-policy']=='no-referrer'
    fallback=client().get('/auth/login')
    for response in (page,fallback):
        for name in ('header','footer'):
            assert (ROOT/'frontend/shared'/f'{name}.html').read_text().strip() in response.text
        assert 'frame-ancestors \'none\'' in response.headers['content-security-policy']
        assert "script-src 'self'" in response.headers['content-security-policy']
    for forbidden in ('홈페이지로','MY LEARNING JOURNEY','조회 버전','계정으로 계속해서 이용하세요','카카오 회원님'):
        assert forbidden not in page.text+fallback.text
    assert '사이드바' not in page.text and 'class="sidebar"' not in page.text
    assert '회원탈퇴 문의' in page.text
    assert 'href="tel:0322368944"' in page.text
    # No pretend mutation buttons or fake learning history are added.
    for forbidden in ('onclick=','/withdraw','수강 중 (1)','010-1234-5678','kakao_user@'):
        assert forbidden not in page.text


@pytest.mark.parametrize('name',['site.css','site.js','login.js','account.css','account.js'])
def test_shared_assets_are_available_without_customer_queries(monkeypatch,name):
    app=app_with_portal(monkeypatch)
    r=TestClient(app).get('/portal/assets/'+name)
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    assert r.content==(ROOT/'frontend/shared'/name).read_bytes()
    assert TestClient(app).get('/portal/assets/site-header.html').status_code==404


def test_account_scripts_store_no_identity_or_session_state():
    for filename in ('account.js','login.js','site.js'):
        source=(ROOT/'frontend/shared'/filename).read_text()
        for forbidden in ('localStorage','sessionStorage','document.cookie','innerHTML','eval('):
            assert forbidden not in source
    assert 'textContent' in (ROOT/'frontend/shared/account.js').read_text()
