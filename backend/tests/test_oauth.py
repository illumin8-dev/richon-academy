from dataclasses import replace
from urllib.parse import urlsplit,parse_qs
from unittest.mock import Mock
import re
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import oauth_providers as p,oauth_http as h,oauth_store as s
from auth_core import VerifiedIdentity
ORIGIN='https://richon.example.invalid'


def settings():
    return p.Settings(ORIGIN,{'kakao':p.Provider('kakao','test-kakao','test-secret',1585992),'naver':p.Provider('naver','test-naver','test-secret')},'test-terms-v1','test-privacy-v1',ORIGIN+'/terms',ORIGIN+'/privacy')


def app():
    a=FastAPI();a.include_router(h.make_router(settings()));return a


def test_disabled_needs_explicit_keys_and_origin(monkeypatch):
    a=FastAPI();monkeypatch.delenv('RICHON_OAUTH_ENABLED',raising=False)
    assert h.install_if_enabled(a) is False
    assert TestClient(a).get('/auth/login').status_code==404
    monkeypatch.setenv('RICHON_OAUTH_ENABLED','true')
    with pytest.raises(ValueError):h.install_if_enabled(a)
    for key in ['KAKAO_CLIENT_ID','KAKAO_CLIENT_SECRET','KAKAO_APP_ID','NAVER_CLIENT_ID','NAVER_CLIENT_SECRET','RICHON_OAUTH_ORIGIN']:monkeypatch.delenv(key,raising=False)
    with pytest.raises(ValueError):p.Settings.from_env()


@pytest.mark.parametrize('origin',['http://bad.invalid','https://bad.invalid/','https://name:pass@bad.invalid','https://*.bad.invalid'])
def test_reject_invalid_origins(origin):
    with pytest.raises(ValueError):replace(settings(),origin=origin)


def test_provider_specific_callback_and_kakao_pkce():
    cfg=settings();browser='B'*43;state='S'*43
    for name in cfg.providers:
        q=parse_qs(urlsplit(p.authorization_url(cfg,name,state,browser)).query)
        assert q['redirect_uri']==[ORIGIN+'/auth/'+name+'/callback']
        assert q['state']==[state] and 'client_secret' not in q
        assert ('code_challenge' in q)==(name=='kakao')
    assert p.verifier(browser,state)!=p.verifier('C'*43,state)


@pytest.mark.parametrize('name',['kakao','naver'])
def test_exchange_fixed_endpoints_no_unverified_jwt(monkeypatch,name):
    cfg=settings();seen=[]
    def respond(r):
        seen.append(r)
        if str(r.url)==p.ENDPOINTS[name][1]:
            values=parse_qs(r.content.decode());assert values['client_secret']==['test-secret']
            assert ('code_verifier' in values)==(name=='kakao')
            return httpx.Response(200,json={'access_token':'synthetic-access','token_type':'bearer','id_token':'unverified-ignored'})
        assert r.headers['authorization']=='Bearer synthetic-access'
        if 'access_token_info' in str(r.url):return httpx.Response(200,json={'id':42,'app_id':1585992,'expires_in':500})
        return httpx.Response(200,json={'id':42,'kakao_account':{'profile':{'nickname':'가상 사용자'}}} if name=='kakao' else {'resultcode':'00','response':{'id':'naver-scoped-42','nickname':'가상 사용자','email':'ignored@example.invalid'}})
    monkeypatch.setattr(p,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond),follow_redirects=False))
    identity=p.exchange(cfg,name,'synthetic-code','S'*43,'B'*43)
    assert identity==VerifiedIdentity(name,cfg.providers[name].identity_scope,'42' if name=='kakao' else 'naver-scoped-42','가상 사용자')
    assert all(r.url.host in {'kauth.kakao.com','kapi.kakao.com','nid.naver.com','openapi.naver.com'} for r in seen)


@pytest.mark.parametrize('fault',['redirect','missing_token','wrong_app','wrong_subject','bad_profile','too_large'])
def test_provider_failure_closed(monkeypatch,fault):
    def respond(r):
        if str(r.url).endswith('/oauth/token'):
            if fault=='redirect':return httpx.Response(302,headers={'location':'https://evil.example.invalid'})
            if fault=='missing_token':return httpx.Response(200,json={'access_token':True,'token_type':'bearer'})
            if fault=='too_large':return httpx.Response(200,content=b' '*70000)
            return httpx.Response(200,json={'access_token':'synthetic','token_type':'bearer'})
        if 'access_token_info' in str(r.url):return httpx.Response(200,json={'id':43 if fault=='wrong_subject' else 42,'app_id':999 if fault=='wrong_app' else 1585992,'expires_in':100})
        return httpx.Response(200,json={'id':True if fault=='bad_profile' else 42})
    monkeypatch.setattr(p,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond),follow_redirects=False))
    with pytest.raises(p.ProviderRejected):p.exchange(settings(),'kakao','code','S'*43,'B'*43)


def test_login_page_no_secrets_and_csrf_boundary(monkeypatch):
    c=TestClient(app(),base_url=ORIGIN)
    r=c.get('/auth/login');assert r.status_code==200 and 'test-secret' not in r.text and 'test-kakao' not in r.text
    assert 'HttpOnly' in r.headers['set-cookie'] and 'Secure' in r.headers['set-cookie']
    assert r.headers['cache-control']=='no-store'
    csrf=re.search(r'name="csrf" value="([^"]+)"',r.text)[1]
    fn=Mock();monkeypatch.setattr(s,'begin',fn)
    for data,headers in [({'csrf':'bad','provider':'kakao'},{'Origin':ORIGIN}),({'csrf':csrf,'provider':'kakao'},{'Origin':'https://evil.example.invalid'})]:
        assert c.post('/auth/start',data=data,headers=headers).status_code==403
    assert c.post('/auth/start',data={'csrf':csrf,'provider':'kakao','return_to':'//evil.invalid'},headers={'Origin':ORIGIN}).status_code==422
    fn.assert_not_called()


def test_callback_invalid_state_never_exchanges(monkeypatch):
    exchange=Mock();monkeypatch.setattr(p,'exchange',exchange)
    c=TestClient(app(),base_url=ORIGIN);c.get('/auth/login')
    for url in ['/auth/kakao/callback?code=secret&state=bad','/auth/naver/callback?state=A&state=B','/auth/evil/callback?state=A']:
        r=c.get(url,follow_redirects=False)
        assert r.status_code==303 and r.headers['location']=='/auth/login?error=login_failed'
        assert 'secret' not in r.text
    exchange.assert_not_called()


def test_kakao_only_config_uses_confirmed_app_id(monkeypatch):
    env={'KAKAO_CLIENT_ID':'synthetic-rest-key','KAKAO_CLIENT_SECRET':'synthetic-secret',
         'RICHON_OAUTH_ORIGIN':ORIGIN,'RICHON_AUTH_ALLOWED_ORIGINS':ORIGIN,
         'RICHON_TERMS_VERSION':'test-terms-v1','RICHON_PRIVACY_VERSION':'test-privacy-v1',
         'RICHON_TERMS_URL':ORIGIN+'/terms','RICHON_PRIVACY_URL':ORIGIN+'/privacy'}
    for key in ['NAVER_CLIENT_ID','NAVER_CLIENT_SECRET','KAKAO_APP_ID']:monkeypatch.delenv(key,raising=False)
    for key,value in env.items():monkeypatch.setenv(key,value)
    cfg=p.Settings.from_env()
    assert list(cfg.providers)==['kakao']
    assert cfg.providers['kakao'].kakao_app_id==1585992 and cfg.providers['kakao'].identity_scope=='1585992'
    a=FastAPI();a.include_router(h.make_router(cfg))
    response=TestClient(a,base_url=ORIGIN).get('/auth/login')
    assert '카카오로 로그인' in response.text and '네이버로 로그인' not in response.text
    assert 'synthetic-rest-key' not in response.text and 'synthetic-secret' not in response.text


@pytest.mark.parametrize('info',[
    {'id':42,'app_id':1585993,'expires_in':500}, {'id':42,'app_id':'1585992','expires_in':500},
    {'id':True,'app_id':1585992,'expires_in':500}, {'id':42,'app_id':1585992,'expires_in':0},
    {'id':42,'app_id':1585992,'expires_in':-1}, {'id':42,'app_id':1585992,'expires_in':'500'},
])
def test_bad_kakao_token_info_rejected_before_profile(monkeypatch,info):
    seen=[]
    def respond(request):
        seen.append(request.url.path)
        if request.url.path=='/oauth/token':return httpx.Response(200,json={'token_type':'bearer','access_token':'synthetic'})
        if request.url.path.endswith('access_token_info'):return httpx.Response(200,json=info)
        pytest.fail('Unverified app/expiry must not query a profile')
    monkeypatch.setattr(p,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(p.ProviderRejected):p.exchange(settings(),'kakao','code','S'*43,'B'*43)
    assert '/v2/user/me' not in seen


@pytest.mark.parametrize('account,expected',[
    ({'profile':{'nickname':'가상 별명'}},'가상 별명'),({'profile_nickname_needs_agreement':True},'카카오 회원'),(None,'카카오 회원'),
])
def test_optional_nickname_never_blocks_login(monkeypatch,account,expected):
    def respond(request):
        if request.url.path=='/oauth/token':return httpx.Response(200,json={'token_type':'bearer','access_token':'synthetic'})
        if request.url.path.endswith('access_token_info'):return httpx.Response(200,json={'id':42,'app_id':1585992,'expires_in':500})
        assert parse_qs(request.url.query.decode())['property_keys']==['["kakao_account.profile"]']
        return httpx.Response(200,json={'id':42,'kakao_account':account})
    monkeypatch.setattr(p,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond)))
    identity=p.exchange(settings(),'kakao','code','S'*43,'B'*43)
    assert identity.app_id=='1585992' and identity.display_name==expected


def test_rest_key_rotation_preserves_kakao_identity_scope():
    original=settings().providers['kakao']
    assert replace(original,client_id='rotated-rest-key').identity_scope==original.identity_scope


def test_signup_proof_is_bound_to_current_ticket(monkeypatch):
    c=TestClient(app(),base_url=ORIGIN)
    c.cookies.set(h.BROWSER,'B'*43,domain='richon.example.invalid',path='/')
    c.cookies.set(h.TICKET,'C'*43,domain='richon.example.invalid',path='/')
    data={'csrf':h.proof('B'*43,'D'*43),'terms':'yes','privacy':'yes','terms_version':settings().terms_version,'privacy_version':settings().privacy_version}
    pending=Mock();monkeypatch.setattr(s,'pending',pending)
    assert c.post('/auth/signup',data=data,headers={'Origin':ORIGIN}).status_code==403
    pending.assert_not_called()


@pytest.mark.parametrize('body,ctype,status',[
    ('csrf=a&csrf=b','application/x-www-form-urlencoded',422),
    ('csrf='+('a'*4100),'application/x-www-form-urlencoded',413),('{"csrf":"x"}','application/json',415),
])
def test_start_form_limits_before_db(monkeypatch,body,ctype,status):
    begin=Mock();monkeypatch.setattr(s,'begin',begin)
    c=TestClient(app(),base_url=ORIGIN);c.get('/auth/login')
    assert c.post('/auth/start',content=body,headers={'Origin':ORIGIN,'Content-Type':ctype}).status_code==status
    begin.assert_not_called()


def test_duplicate_cookie_and_unconfigured_provider_fail_closed(monkeypatch):
    cfg=replace(settings(),providers={'kakao':settings().providers['kakao']})
    a=FastAPI();a.include_router(h.make_router(cfg))
    c=TestClient(a,base_url=ORIGIN)
    response=c.get('/auth/kakao/callback',params={'state':'S'*43,'code':'synthetic'},headers={'Cookie':h.BROWSER+'='+'B'*43+'; '+h.BROWSER+'='+'C'*43},follow_redirects=False)
    assert response.headers['location']=='/auth/login?error=login_failed'
    assert c.get('/auth/naver/callback?state=x&code=x',follow_redirects=False).status_code==303
