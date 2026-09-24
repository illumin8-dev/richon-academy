"""Kakao/Naver confidential-server OAuth adapters; no client-supplied identities."""
from dataclasses import dataclass, field
import base64
import hashlib
import hmac
import json
import os
import re
import unicodedata
from urllib.parse import urlencode, urlsplit
import httpx
import member_profile
from auth_core import VerifiedIdentity, SignupConsent
from auth_http import AuthSettings

ENDPOINTS = {
    'kakao': ('https://kauth.kakao.com/oauth/authorize', 'https://kauth.kakao.com/oauth/token', 'https://kapi.kakao.com/v2/user/me'),
    'naver': ('https://nid.naver.com/oauth2.0/authorize', 'https://nid.naver.com/oauth2.0/token', 'https://openapi.naver.com/v1/nid/me'),
}
RICHON_KAKAO_APP_ID = 1585992
PUBLIC_RETURNS = frozenset({'/', '/index.html', '/apply.html'})
RETURNS = PUBLIC_RETURNS | frozenset({'/portal/mypage','/portal/admin','/portal/enrollments','/portal/manual'})

class ProviderRejected(Exception):
    """Safe fixed error; never contains provider response bodies or credentials."""

@dataclass(frozen=True)
class Provider:
    name: str
    client_id: str = field(repr=False)
    secret: str = field(repr=False)
    kakao_app_id: int | None = None

    def __post_init__(self):
        if self.name not in ENDPOINTS: raise ValueError('invalid_oauth_provider')
        for value in (self.client_id,self.secret):
            if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',value):
                raise ValueError('invalid_oauth_credentials')
        if self.name=='kakao' and (type(self.kakao_app_id) is not int or self.kakao_app_id<=0):
            raise ValueError('kakao_app_id_required')

    @property
    def identity_scope(self) -> str:
        # REST key rotation must not create a new member in the same Kakao app.
        return str(self.kakao_app_id) if self.name=='kakao' else self.client_id

@dataclass(frozen=True)
class Settings:
    origin: str
    providers: dict[str,Provider]
    terms_version: str
    privacy_version: str
    terms_url: str
    privacy_url: str

    def __post_init__(self):
        AuthSettings(frozenset({self.origin}))
        SignupConsent(self.terms_version,self.privacy_version)
        member_profile.enabled(self.terms_version, self.privacy_version)
        if not self.providers or any(n!=p.name for n,p in self.providers.items()):
            raise ValueError('oauth_provider_required')
        for url in (self.terms_url,self.privacy_url):
            u=urlsplit(url)
            if u.scheme!='https' or not u.hostname or u.username or u.password or u.fragment or u.query or len(url)>512:
                raise ValueError('approved_policy_url_required')

    def callback(self,name):
        if name not in self.providers: raise ProviderRejected()
        return self.origin+'/auth/'+name+'/callback'

    @classmethod
    def from_env(cls):
        configured={}
        for name in ENDPOINTS:
            cid=os.getenv(name.upper()+'_CLIENT_ID','')
            secret=os.getenv(name.upper()+'_CLIENT_SECRET','')
            if cid or secret:
                app=int(os.getenv('KAKAO_APP_ID',str(RICHON_KAKAO_APP_ID))) if name=='kakao' else None
                configured[name]=Provider(name,cid,secret,app)
        settings=cls(os.getenv('RICHON_OAUTH_ORIGIN',''),configured,
                     os.getenv('RICHON_TERMS_VERSION',''),os.getenv('RICHON_PRIVACY_VERSION',''),
                     os.getenv('RICHON_TERMS_URL',''),os.getenv('RICHON_PRIVACY_URL',''))
        allowed={x.strip() for x in os.getenv('RICHON_AUTH_ALLOWED_ORIGINS','').split(',')}
        if settings.origin not in allowed: raise ValueError('oauth_origin_not_allowed')
        return settings

def verifier(browser,state):
    digest=hmac.new(browser.encode(),('richon/pkce/v1/'+state).encode(),hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()

def authorization_url(settings,name,state,browser):
    provider=settings.providers[name]
    args={'response_type':'code','client_id':provider.client_id,'redirect_uri':settings.callback(name),'state':state}
    if name=='kakao':
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier(browser,state).encode()).digest()).rstrip(b'=').decode()
        args.update(code_challenge=challenge,code_challenge_method='S256')
    return ENDPOINTS[name][0]+'?'+urlencode(args)

def _json(client,method,url,**kwargs):
    try:
        with client.stream(method,url,**kwargs) as response:
            if response.status_code!=200: raise ProviderRejected()
            chunks=[];size=0
            for block in response.iter_bytes():
                size+=len(block)
                if size>65536: raise ProviderRejected()
                chunks.append(block)
            result=json.loads(b''.join(chunks))
            if not isinstance(result,dict): raise ProviderRejected()
            return result
    except Exception: raise ProviderRejected() from None

def _client():
    return httpx.Client(timeout=httpx.Timeout(8.0),follow_redirects=False,trust_env=False)

def exchange(settings,name,code,state,browser):
    provider=settings.providers[name]
    form={'grant_type':'authorization_code','client_id':provider.client_id,'client_secret':provider.secret,
          'redirect_uri':settings.callback(name),'code':code,'state':state}
    if name=='kakao': form['code_verifier']=verifier(browser,state)
    with _client() as client:
        token=_json(client,'POST',ENDPOINTS[name][1],data=form)
        access=token.get('access_token')
        if (not isinstance(access,str) or not re.fullmatch(r'[A-Za-z0-9._~+/-]{1,8192}={0,2}',access)
            or str(token.get('token_type','')).lower()!='bearer' or token.get('error')):
            raise ProviderRejected()
        headers={'Authorization':'Bearer '+access}
        if name=='kakao':
            info=_json(client,'GET','https://kapi.kakao.com/v1/user/access_token_info',headers=headers)
            if (type(info.get('id')) is not int or info['id']<=0
                or type(info.get('app_id')) is not int or info['app_id']!=provider.kakao_app_id
                or type(info.get('expires_in')) is not int or info['expires_in']<=0):
                raise ProviderRejected()
            profile=_json(client,'GET',ENDPOINTS[name][2],headers=headers,
                          params={'property_keys':json.dumps(['kakao_account.name'] if member_profile.enabled(settings.terms_version, settings.privacy_version) else ['kakao_account.profile'])})
            subject=profile.get('id')
            if type(subject) is not int or subject!=info['id']: raise ProviderRejected()
            account=profile.get('kakao_account')
            details=account.get('profile') if isinstance(account,dict) else None
            nickname=details.get('nickname') if isinstance(details,dict) else None
        else:
            profile=_json(client,'GET',ENDPOINTS[name][2],headers=headers)
            response=profile.get('response')
            if profile.get('resultcode')!='00' or not isinstance(response,dict): raise ProviderRejected()
            subject=response.get('id');nickname=response.get('nickname')
            if not isinstance(subject,str) or not 1<=len(subject)<=255: raise ProviderRejected()
        if member_profile.enabled(settings.terms_version, settings.privacy_version):
            nickname = account.get('name') if name == 'kakao' and isinstance(account, dict) else (response.get('name') if name == 'naver' else None)
        display=nickname if isinstance(nickname,str) else ''
        display=''.join(c for c in display if not unicodedata.category(c).startswith('C')).strip()[:80]
        if not display: display='회원' if member_profile.enabled(settings.terms_version, settings.privacy_version) else ('카카오 회원' if name=='kakao' else '네이버 회원')
        try: return VerifiedIdentity(name,provider.identity_scope,str(subject),display)
        except ValueError: raise ProviderRejected() from None
