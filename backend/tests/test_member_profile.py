"""Approved profile rules and HTTP paths. Only synthetic data and mocked providers."""
from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4
from urllib.parse import parse_qs,urlsplit
import re
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import member_profile as m
import member_profile_store as ms
import oauth_http as h
import oauth_providers as p
import oauth_store as s
import auth_core as core
import identity_verification as iv
from test_oauth import settings, ORIGIN


def cfg():
    return replace(settings(), terms_version=m.VERSION, privacy_version=m.VERSION)


def data():
    return dict(name='테스트 이름', phone='010-1234-5678', email='tester@example.invalid',
                terms='yes', privacy='yes', over14='yes', terms_version=m.VERSION, privacy_version=m.VERSION)


def client():
    a=FastAPI();a.include_router(h.make_router(cfg()))
    return TestClient(a, base_url=ORIGIN)


def enable_identity(monkeypatch):
    monkeypatch.setenv('RICHON_IDENTITY_VERIFICATION_ENABLED','true')
    monkeypatch.setenv('PORTONE_STORE_ID','store-12345678')
    monkeypatch.setenv('PORTONE_IDENTITY_CHANNEL_KEY','channel-key-12345678')
    monkeypatch.setenv('PORTONE_API_SECRET','synthetic-secret-value-1234567890')


@pytest.mark.parametrize('field', ['name','phone','email','terms','privacy','over14','terms_version','privacy_version'])
def test_missing_required_is_rejected(field):
    form=data();form.pop(field)
    with pytest.raises(m.InvalidProfile):m.Registration.from_form(form)


@pytest.mark.parametrize('field,value',[('name','<script>'),('name','abc\n'),('phone','010<script>'),('phone','１２３４５６７８'),('email','a\r\n@invalid.example'),('email','a@example.invalid\r\n'),('email','..a@example.invalid'),('email','a@-x.invalid'),('email','a@@example.invalid')])
def test_invalid_values_never_echo_personal_information(field,value):
    with pytest.raises(m.InvalidProfile) as exc:m.Registration.from_form({**data(),field:value})
    assert value not in str(exc.value)


def test_optional_values_discarded_without_consent_and_no_repr_leak():
    form={**data(),'age_range':'malicious','gender':'malicious'}
    result=m.Registration.from_form(form)
    assert result.age_range is None and result.gender is None
    assert result.consultation_consent is False and result.marketing_consent is False
    assert form['name'] not in repr(result) and form['email'] not in repr(result)


def test_marketing_consent_is_explicit_and_never_required():
    assert m.Registration.from_form(data()).marketing_consent is False
    assert m.Registration.from_form({**data(),'marketing':'yes'}).marketing_consent is True
    with pytest.raises(m.InvalidProfile):
        m.Registration.from_form({**data(),'marketing':'no'})


def test_consented_choices_and_partial_optional_values():
    result=m.Registration.from_form({**data(),'consultation':'yes','age_range':'30-39','gender':'female'})
    assert result.age_range=='30-39' and result.gender=='female'
    assert m.Registration.from_form({**data(),'consultation':'yes'}).age_range is None
    with pytest.raises(m.InvalidProfile):m.Registration.from_form({**data(),'consultation':'yes','gender':'unlisted'})
    with pytest.raises(m.InvalidProfile):m.Registration.from_form({**data(),'consultation':'no'})


def test_required_normalization_and_explicit_activation():
    r=m.Registration.from_form({**data(),'phone':'+82 10-1234-5678','email':'Tester@EXAMPLE.invalid'})
    assert r.phone=='01012345678' and r.email=='Tester@example.invalid'
    assert not m.enabled('internal-test-v1','internal-test-v1')
    assert m.enabled(m.VERSION,m.VERSION)
    with pytest.raises(ValueError):replace(settings(),terms_version=m.VERSION)


@pytest.mark.parametrize('provider',['kakao','naver'])
def test_age_confirmation_is_signup_only(monkeypatch,provider):
    c=client();r=c.get('/auth/login');csrf=re.search(r'name="csrf" value="([^"]+)"',r.text)[1]
    assert 'name="over14"' not in r.text
    assert '회원 관리와 상담에 필요한 정보를 수집합니다.' in r.text
    begin=Mock(return_value='S'*43);monkeypatch.setattr(s,'begin',begin)
    form={'csrf':csrf,'provider':provider,'return_to':'/portal/mypage'}
    response=c.post('/auth/start',data=form,headers={'Origin':ORIGIN},follow_redirects=False)
    assert response.status_code==200 and 'data-richon-provider-handoff' in response.text
    assert begin.call_count==1
    assert c.post('/auth/start',data={**form,'over14':'yes'},headers={'Origin':ORIGIN},follow_redirects=False).status_code==422



def test_signup_form_is_unchecked_and_has_required_real_fields(monkeypatch):
    monkeypatch.setenv('RICHON_MARKETING_CONSENT_ENABLED','true')
    monkeypatch.setattr(s,'pending',Mock(return_value=(core.VerifiedIdentity('naver','test-naver','subject','회원'),'/')))
    monkeypatch.setattr(s,'signup_profile',Mock(return_value=p.ProviderProfile()))
    c=client();c.cookies.set(h.BROWSER,'B'*43);c.cookies.set(h.TICKET,'T'*43)
    r=c.get('/auth/signup')
    assert r.status_code==200 and 'name="name"' in r.text and 'name="phone"' in r.text and 'name="email"' in r.text
    assert ' checked' not in r.text and '[선택] 상담정보' in r.text and '기본 회원 서비스를 이용' in r.text
    assert 'data-consent-all' in r.text and 'name="marketing"' in r.text
    assert '광고성 정보 수신 동의 (문자·이메일)' in r.text
    assert 'CI(연계정보)' in r.text and '중복 회원가입 방지' in r.text
    assert r.text.index('선택 / 연령대·성별') < r.text.index('필수 / 만 14세 이상 자기확인')
    assert 'value="회원"' not in r.text and 'name="password"' not in r.text


def test_signup_requires_server_verified_identity(monkeypatch):
    enable_identity(monkeypatch)
    monkeypatch.setattr(s,'pending',Mock(return_value=(core.VerifiedIdentity('naver','test-naver','subject','회원'),'/')))
    monkeypatch.setattr(s,'signup_profile',Mock(return_value=p.ProviderProfile()))
    finish=Mock(return_value=(uuid4(),'/apply.html'));monkeypatch.setattr(ms,'finish',finish)
    monkeypatch.setattr(h,'complete',lambda mid,request,target:h.redirect(target))
    person=iv.VerifiedPerson('a'*64)
    verify=Mock(return_value=person);monkeypatch.setattr(iv,'verify',verify)

    c=client();c.cookies.set(h.BROWSER,'B'*43);c.cookies.set(h.TICKET,'T'*43)
    page=c.get('/auth/signup')
    assert page.status_code==200
    assert 'https://cdn.portone.io/v2/browser-sdk.js' in page.text
    assert '휴대전화 본인확인 [필수]' in page.text
    identity_id=re.search(r'data-verification-id="([^"]+)"',page.text)[1]
    csrf=re.search(r'name="csrf" value="([^"]+)"',page.text)[1]
    base={**data(),'csrf':csrf}

    rejected=c.post('/auth/signup',data=base,headers={'Origin':ORIGIN},follow_redirects=False)
    assert rejected.status_code==303 and rejected.headers['location']=='/auth/signup?identity_error=verification_failed'
    finish.assert_not_called();verify.assert_not_called()

    accepted=c.post('/auth/signup',data={**base,'identity_verification_id':identity_id},
                    headers={'Origin':ORIGIN},follow_redirects=False)
    assert accepted.status_code==303 and accepted.headers['location']=='/apply.html'
    verify.assert_called_once()
    assert finish.call_args.args[-1] is person


def test_mobile_identity_redirect_is_server_verified_before_marking_complete(monkeypatch):
    enable_identity(monkeypatch)
    monkeypatch.setattr(s,'pending',Mock(return_value=(core.VerifiedIdentity('kakao','test-kakao','subject','회원'),'/')))
    monkeypatch.setattr(s,'signup_profile',Mock(return_value=p.ProviderProfile()))
    person=iv.VerifiedPerson('b'*64)
    verify=Mock(return_value=person);monkeypatch.setattr(iv,'verify',verify)

    c=client();c.cookies.set(h.BROWSER,'B'*43);c.cookies.set(h.TICKET,'T'*43)
    first=c.get('/auth/signup')
    identity_id=re.search(r'data-verification-id="([^"]+)"',first.text)[1]
    returned=c.get('/auth/signup',params={'identityVerificationId':identity_id})
    assert returned.status_code==200
    assert 'data-identity-verified="true"' in returned.text
    assert f'name="identity_verification_id" value="{identity_id}"' in returned.text
    assert verify.call_count==1


def test_identity_verification_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv('RICHON_IDENTITY_VERIFICATION_ENABLED','true')
    monkeypatch.delenv('PORTONE_STORE_ID',raising=False)
    monkeypatch.delenv('PORTONE_IDENTITY_CHANNEL_KEY',raising=False)
    monkeypatch.delenv('PORTONE_API_SECRET',raising=False)
    with pytest.raises(ValueError):
        client()


def test_signup_validates_before_save_and_does_not_echo_fields(monkeypatch):
    monkeypatch.setenv('RICHON_MARKETING_CONSENT_ENABLED','true')
    c=client();c.cookies.set(h.BROWSER,'B'*43);c.cookies.set(h.TICKET,'T'*43)
    finish=Mock(return_value=(uuid4(),'/apply.html'));monkeypatch.setattr(ms,'finish',finish)
    monkeypatch.setattr(h,'complete',lambda mid,request,target:h.redirect(target))
    base={**data(),'csrf':h.proof('B'*43,'T'*43)}
    r=c.post('/auth/signup',data={**base,'phone':'bad-private-phone'},headers={'Origin':ORIGIN})
    assert r.status_code==422 and 'bad-private-phone' not in r.text;finish.assert_not_called()
    r=c.post('/auth/signup',data={**base,'age_range':'30-39','gender':'female'},headers={'Origin':ORIGIN},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/apply.html'
    saved=finish.call_args.args[-1];assert saved.age_range is None and saved.gender is None
    assert saved.marketing_consent is False
    r=c.post('/auth/signup',data={**base,'marketing':'no'},headers={'Origin':ORIGIN})
    assert r.status_code==422


@pytest.mark.parametrize('completed',[False,True])
def test_existing_member_needs_profile_not_a_new_identity(monkeypatch,completed):
    mid=uuid4();c=client();c.get('/auth/login')
    monkeypatch.setattr(s,'consume_attempt',Mock(return_value='/'))
    verified=p.VerifiedProviderSession(
        core.VerifiedIdentity('naver','test-naver','id','실제 이름'),'synthetic',
        p.ProviderProfile(name='실제 이름'))
    monkeypatch.setattr(p,'exchange_session',Mock(return_value=verified))
    monkeypatch.setattr(s,'member_for',Mock(return_value=mid))
    monkeypatch.setattr(ms,'completed',Mock(return_value=completed))
    stage=Mock(return_value='T'*43);monkeypatch.setattr(s,'stage_signup',stage)
    complete=Mock(return_value=h.redirect('/'));monkeypatch.setattr(h,'complete',complete)
    r=c.get('/auth/naver/callback?state='+('S'*43)+'&code=synthetic',follow_redirects=False)
    assert r.headers['location']==('/' if completed else '/auth/signup')
    assert complete.called is completed and stage.called is not completed


@pytest.mark.parametrize('provider',['kakao','naver'])
def test_v1_collects_valid_provider_signup_profile_without_using_nickname(monkeypatch,provider):
    seen=[]
    def respond(r):
        seen.append(str(r.url))
        if r.url.host in {'kauth.kakao.com','nid.naver.com'} and r.url.path.endswith('/token'):
            return httpx.Response(200,json={'access_token':'synthetic','token_type':'bearer'})
        if 'access_token_info' in str(r.url):
            return httpx.Response(200,json={'id':42,'app_id':1585992,'expires_in':100})
        if provider=='kakao':
            return httpx.Response(200,json={'id':42,'kakao_account':{
                'name':'제공자 이름','email':'provider@example.invalid','phone_number':'+82 10-2222-3333',
                'age_range':'30~39','gender':'female','ci':'synthetic-ci-value-1234567890',
                'profile':{'nickname':'NEVER_AS_NAME'}}})
        return httpx.Response(200,json={'resultcode':'00','response':{
            'id':'uid','name':'제공자 이름','mobile':'010-2222-3333',
            'email':'provider@example.invalid','age':'30-39','gender':'F',
            'nickname':'NEVER_AS_NAME'}})
    monkeypatch.setattr(p,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond)))
    session=p.exchange_session(cfg(),provider,'code','S'*43,'B'*43)
    assert session.identity.display_name=='제공자 이름'
    expected_ci=p._provider_ci_digest('synthetic-ci-value-1234567890') if provider=='kakao' else None
    assert session.profile==p.ProviderProfile('제공자 이름','01022223333','provider@example.invalid','30-39','female',expected_ci)
    assert 'NEVER_AS_NAME' not in repr(session.identity)
    if provider=='kakao':
        profile_url=next(url for url in seen if '/v2/user/me' in url)
        keys=parse_qs(urlsplit(profile_url).query)['property_keys'][0]
        assert all(field in keys for field in ('kakao_account.name','kakao_account.email',
                                                'kakao_account.phone_number','kakao_account.age_range',
                                                'kakao_account.gender','kakao_account.ci'))


@pytest.mark.parametrize('provider',['kakao','naver'])
def test_v1_missing_or_invalid_provider_profile_fields_fall_back_to_signup_input(monkeypatch,provider):
    def respond(r):
        if str(r.url)==p.ENDPOINTS[provider][1]:
            return httpx.Response(200,json={'access_token':'synthetic','token_type':'bearer'})
        if 'access_token_info' in str(r.url):
            return httpx.Response(200,json={'id':42,'app_id':1585992,'expires_in':100})
        if provider=='kakao':
            return httpx.Response(200,json={'id':42,'kakao_account':{
                'name':'제공자 이름','email':'not-an-email','phone_number':'not-a-phone',
                'age_range':'10~14','gender':'unknown'}})
        return httpx.Response(200,json={'resultcode':'00','response':{
            'id':'uid','name':'제공자 이름','mobile':'not-a-phone','email':'not-an-email',
            'age':'10-19','gender':'U'}})
    monkeypatch.setattr(p,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond)))
    session=p.exchange_session(cfg(),provider,'code','S'*43,'B'*43)
    assert session.profile.name=='제공자 이름'
    assert session.profile.phone is None and session.profile.email is None
    assert session.profile.age_range is None and session.profile.gender is None


def test_signup_form_locks_only_provider_supplied_fields(monkeypatch):
    monkeypatch.setattr(s,'pending',Mock(return_value=(core.VerifiedIdentity('naver','test-naver','subject','제공자 이름'),'/')))
    monkeypatch.setattr(s,'signup_profile',Mock(return_value=p.ProviderProfile(
        name='제공자 이름',phone='01022223333',email=None,age_range='30-39',gender='female')))
    c=client();c.cookies.set(h.BROWSER,'B'*43);c.cookies.set(h.TICKET,'T'*43)
    r=c.get('/auth/signup')
    assert r.status_code==200
    assert 'name="name"' in r.text and 'value="제공자 이름"' in r.text
    assert r.text.count('data-provider-locked="true"')==4
    assert 'value="01022223333"' in r.text
    email=re.search(r'<input[^>]*name="email"[^>]*>',r.text)[0]
    assert 'readonly' not in email
    assert 'id="signup-age_range"' in r.text and 'id="signup-gender"' in r.text
    assert 'name="age_range" value="30-39"' in r.text
    assert 'name="gender" value="female"' in r.text
    assert r.text.count('aria-disabled="true"')==2



def test_provider_demographic_normalization_contract():
    assert p._provider_age_range('kakao','15~19')=='14-19'
    assert p._provider_age_range('kakao','20~29')=='20-29'
    assert p._provider_age_range('kakao','70~79')=='70+'
    assert p._provider_age_range('kakao','10~14') is None
    assert p._provider_age_range('naver','20-29')=='20-29'
    assert p._provider_age_range('naver','80-89')=='70+'
    assert p._provider_age_range('naver','10-19') is None
    assert p._provider_gender('kakao','female')=='female'
    assert p._provider_gender('kakao','male')=='male'
    assert p._provider_gender('naver','F')=='female'
    assert p._provider_gender('naver','M')=='male'
    assert p._provider_gender('naver','U') is None


def test_ci_digest_contract():
    value='synthetic-ci-value-1234567890'
    digest=p._provider_ci_digest(value)
    assert re.fullmatch(r'[a-f0-9]{64}',digest)
    assert value not in digest
    assert p._provider_ci_digest(' short ') is None
