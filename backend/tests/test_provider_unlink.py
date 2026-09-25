"""Provider-side unlink contracts with synthetic tokens and mocked HTTP only."""
from urllib.parse import parse_qs, urlsplit
import httpx
import pytest

import auth_core as core
import oauth_providers as providers
from test_member_profile import cfg


def session(name,subject,token='synthetic-access-token'):
    identity=core.VerifiedIdentity(name,cfg().providers[name].identity_scope,str(subject),'회원')
    return providers.VerifiedProviderSession(identity,token)


def test_verified_provider_session_hides_access_token():
    value=session('naver','synthetic-user')
    assert 'synthetic-access-token' not in repr(value)


def test_kakao_unlink_uses_fresh_access_token_and_verifies_subject(monkeypatch):
    seen={}
    def respond(request):
        seen['method']=request.method;seen['url']=str(request.url)
        seen['authorization']=request.headers.get('authorization')
        return httpx.Response(200,json={'id':42})
    monkeypatch.setattr(providers,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond),follow_redirects=False))
    providers.unlink_access(cfg(),session('kakao',42))
    assert seen=={'method':'POST','url':'https://kapi.kakao.com/v1/user/unlink',
                  'authorization':'Bearer synthetic-access-token'}


def test_naver_unlink_revokes_token_pair_without_persisting_token(monkeypatch):
    seen={}
    def respond(request):
        seen['method']=request.method;seen['url']=str(request.url)
        seen['form']=parse_qs(request.content.decode())
        return httpx.Response(200,content=b'')
    monkeypatch.setattr(providers,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond),follow_redirects=False))
    settings=cfg();providers.unlink_access(settings,session('naver','synthetic-user'))
    assert seen['method']=='POST' and seen['url']=='https://nid.naver.com/oauth2.0/revoke'
    assert seen['form']['client_id']==[settings.providers['naver'].client_id]
    assert seen['form']['client_secret']==[settings.providers['naver'].secret]
    assert seen['form']['token']==['synthetic-access-token']
    assert seen['form']['token_type_hint']==['access_token']


@pytest.mark.parametrize('name',('kakao','naver'))
def test_unlink_provider_failure_is_fixed_and_does_not_include_token(monkeypatch,name):
    monkeypatch.setattr(providers,'_client',lambda:httpx.Client(
        transport=httpx.MockTransport(lambda request:httpx.Response(503,json={'error':'private-response'})),
        follow_redirects=False))
    with pytest.raises(providers.ProviderRejected) as exc:
        providers.unlink_access(cfg(),session(name,42 if name=='kakao' else 'user'))
    assert 'synthetic-access-token' not in str(exc.value)


@pytest.mark.parametrize('name,param,value',[('kakao','prompt','login'),('naver','auth_type','reauthenticate')])
def test_sensitive_account_authorization_forces_provider_reauthentication(name,param,value):
    settings=cfg();state='S'*43;browser='B'*43
    url=providers.authorization_url(settings,name,state,browser,reauthenticate=True)
    query=parse_qs(urlsplit(url).query)
    assert query[param]==[value]
    normal=parse_qs(urlsplit(providers.authorization_url(settings,name,state,browser)).query)
    assert param not in normal
