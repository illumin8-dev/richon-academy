from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit,parse_qs
from uuid import uuid4
import os,re
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import auth_core as core,auth_http as auth
import oauth_store as store,oauth_http as h,oauth_providers as p,oauth_migrate,login_return_migrate
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target,auth_postgres,CONSENT
from test_oauth import settings,ORIGIN
pytestmark=pytest.mark.skipif(os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),reason='Requires disposable loopback richon_ci')

@pytest.fixture(scope='module')
def oauth_db(auth_postgres):
    assert oauth_migrate.apply_migration()
    previous=store.begin(settings(),'kakao','B'*43,'/portal/mypage')
    assert login_return_migrate.apply_migration()
    assert store.consume_attempt(settings(),'kakao',previous,'B'*43)=='/portal/mypage'
    return auth_postgres


def test_reentry_and_no_plaintext_state(oauth_db):
    assert oauth_migrate.apply_migration() is False
    b='B'*43;cfg=settings();state=store.begin(cfg,'kakao',b,'/portal/mypage')
    with oauth_db() as c:
        row=c.execute('SELECT state_hash,browser_hash FROM richon.oauth_attempts WHERE state_hash=%s',(core.token_digest(state),)).fetchone()
        assert row==(core.token_digest(state),core.token_digest(b))
    with pytest.raises(store.InvalidFlow):store.consume_attempt(cfg,'naver',state,b)
    with pytest.raises(store.InvalidFlow):store.consume_attempt(cfg,'kakao',state,'C'*43)
    assert store.consume_attempt(cfg,'kakao',state,b)=='/portal/mypage'
    with pytest.raises(store.InvalidFlow):store.consume_attempt(cfg,'kakao',state,b)


def test_state_concurrency_only_one_callback_wins(oauth_db):
    cfg=settings();b='B'*43;state=store.begin(cfg,'naver',b,'/portal/mypage')
    def consume(_):
        try:return store.consume_attempt(cfg,'naver',state,b)
        except store.InvalidFlow:return None
    with ThreadPoolExecutor(max_workers=4) as pool:out=list(pool.map(consume,range(4)))
    assert out.count('/portal/mypage')==1 and out.count(None)==3


def test_expired_state_rejected(oauth_db):
    cfg=settings();b='B'*43;state=store.begin(cfg,'kakao',b,'/portal/mypage')
    with oauth_db() as c:c.execute("UPDATE richon.oauth_attempts SET expires_at=CURRENT_TIMESTAMP-interval '1 second' WHERE state_hash=%s",(core.token_digest(state),))
    with pytest.raises(store.InvalidFlow):store.consume_attempt(cfg,'kakao',state,b)


def client():
    a=FastAPI();a.include_router(auth.make_router(auth.AuthSettings(frozenset({ORIGIN}))));a.include_router(h.make_router(settings()))
    return TestClient(a,base_url=ORIGIN)


def start(c,name,target='/'):
    r=c.get('/auth/login',params={'return_to':target});csrf=re.search(r'name="csrf" value="([^"]+)"',r.text)[1]
    r=c.post('/auth/start',data={'csrf':csrf,'provider':name,'return_to':target},headers={'Origin':ORIGIN},follow_redirects=False)
    assert r.status_code==303
    return parse_qs(urlsplit(r.headers['location']).query)['state'][0]


@pytest.mark.parametrize('name',['kakao','naver'])
def test_full_mock_oauth_new_signup_then_repeat_login(oauth_db,monkeypatch,name):
    cfg=settings();identity=core.VerifiedIdentity(name,cfg.providers[name].identity_scope,uuid4().hex,'가상 회원')
    exchange=Mock(return_value=identity);monkeypatch.setattr(p,'exchange',exchange)
    c=client();state=start(c,name)
    with oauth_db() as db:before=db.execute('SELECT count(*) FROM richon.members').fetchone()[0]
    r=c.get('/auth/'+name+'/callback',params={'code':'synthetic-code','state':state},follow_redirects=False)
    assert r.headers['location']=='/auth/signup' and auth.COOKIE not in r.headers.get('set-cookie','')
    with oauth_db() as db:assert db.execute('SELECT count(*) FROM richon.members').fetchone()[0]==before
    r=c.get('/auth/signup');csrf=re.search(r'name="csrf" value="([^"]+)"',r.text)[1]
    form={'csrf':csrf,'terms':'yes','privacy':'yes','terms_version':cfg.terms_version,'privacy_version':cfg.privacy_version}
    assert c.post('/auth/signup',data={**form,'terms':'no'},headers={'Origin':ORIGIN}).status_code==422
    r=c.post('/auth/signup',data=form,headers={'Origin':ORIGIN},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/'
    assert auth.COOKIE in r.headers.get('set-cookie','')
    me=c.get('/auth/me');assert me.status_code==200 and me.json()['role']=='member'
    assert c.get('/auth/signup',follow_redirects=False).headers['location']=='/auth/login?error=login_failed'
    mid=me.json()['member_id']
    other=client();new=start(other,name)
    r=other.get('/auth/'+name+'/callback',params={'code':'another-code','state':new},follow_redirects=False)
    assert r.headers['location']=='/' and other.get('/auth/me').json()['member_id']==mid
    with oauth_db() as db:
        assert db.execute('SELECT count(*) FROM richon.members').fetchone()[0]==before+1
        assert db.execute('SELECT terms_version,privacy_version FROM richon.members WHERE member_id=%s',(mid,)).fetchone()==(cfg.terms_version,cfg.privacy_version)


def test_cancel_and_token_failure_do_not_issue_session(oauth_db,monkeypatch):
    exchange=Mock(side_effect=p.ProviderRejected());monkeypatch.setattr(p,'exchange',exchange)
    c=client();state=start(c,'naver')
    r=c.get('/auth/naver/callback',params={'state':state,'error':'access_denied','error_description':'PRIVATE'},follow_redirects=False)
    assert r.headers['location']=='/auth/login?error=login_failed' and 'PRIVATE' not in r.text
    exchange.assert_not_called();assert c.get('/auth/me').status_code==401
    c.get('/auth/naver/callback',params={'state':state,'code':'reuse'},follow_redirects=False)
    exchange.assert_not_called()
    state=start(c,'naver');r=c.get('/auth/naver/callback',params={'state':state,'code':'fail'},follow_redirects=False)
    assert exchange.call_count==1 and auth.COOKIE not in r.headers.get('set-cookie','')


def test_same_name_and_different_provider_remain_separate(oauth_db):
    ids=[core.register_verified_identity(core.VerifiedIdentity(n,settings().providers[n].identity_scope,uuid4().hex,'동명 고객'),CONSENT) for n in ('kakao','naver')]
    assert ids[0]!=ids[1]


def test_signup_ticket_is_one_use_under_concurrency(oauth_db):
    cfg=settings();browser='B'*43
    identity=core.VerifiedIdentity('kakao','1585992',uuid4().hex,'가상 회원')
    ticket=store.stage_signup(cfg,identity,browser,'/portal/mypage')
    def consume(_):
        try:return store.pending(cfg,ticket,browser,consume=True)
        except store.InvalidFlow:return None
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(consume,range(4)))
    assert sum(result is not None for result in results)==1


def test_expired_ticket_and_policy_change_rejected(oauth_db):
    from dataclasses import replace
    cfg=settings();browser='B'*43
    identity=core.VerifiedIdentity('kakao','1585992',uuid4().hex,'가상 회원')
    ticket=store.stage_signup(cfg,identity,browser,'/portal/mypage')
    with pytest.raises(store.InvalidFlow):store.pending(cfg,ticket,'C'*43)
    with pytest.raises(store.InvalidFlow):store.pending(replace(cfg,terms_version='changed-v2'),ticket,browser)
    with oauth_db() as db:db.execute("UPDATE richon.oauth_signups SET expires_at=CURRENT_TIMESTAMP-interval '1 second' WHERE ticket_hash=%s",(core.token_digest(ticket),))
    with pytest.raises(store.InvalidFlow):store.pending(cfg,ticket,browser,consume=True)


def test_attempt_commit_failure_prevents_provider_request(oauth_db,monkeypatch):
    c=client();state=start(c,'kakao');exchange=Mock();monkeypatch.setattr(p,'exchange',exchange)
    with oauth_db() as db:
        db.execute("CREATE FUNCTION richon.oauth_test_commit_error() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic commit error'; END; $$")
        db.execute('CREATE CONSTRAINT TRIGGER oauth_test_commit_error AFTER UPDATE ON richon.oauth_attempts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION richon.oauth_test_commit_error()')
    try:
        result=c.get('/auth/kakao/callback',params={'state':state,'code':'synthetic-code'},follow_redirects=False)
        assert result.headers['location']=='/auth/login?error=login_failed';exchange.assert_not_called()
        with oauth_db() as db:assert db.execute('SELECT consumed_at FROM richon.oauth_attempts WHERE state_hash=%s',(core.token_digest(state),)).fetchone()==(None,)
    finally:
        with oauth_db() as db:
            db.execute('DROP TRIGGER oauth_test_commit_error ON richon.oauth_attempts');db.execute('DROP FUNCTION richon.oauth_test_commit_error()')


def test_session_commit_failure_does_not_send_login_cookie(oauth_db,monkeypatch):
    identity=core.VerifiedIdentity('kakao','1585992',uuid4().hex,'가상 회원');monkeypatch.setattr(p,'exchange',Mock(return_value=identity))
    c=client();state=start(c,'kakao');c.get('/auth/kakao/callback',params={'state':state,'code':'synthetic'},follow_redirects=False)
    response=c.get('/auth/signup');csrf=re.search(r'name="csrf" value="([^"]+)"',response.text)[1]
    monkeypatch.setattr(core,'issue_session',Mock(side_effect=RuntimeError('synthetic database error')))
    response=c.post('/auth/signup',data={'csrf':csrf,'terms':'yes','privacy':'yes','terms_version':settings().terms_version,'privacy_version':settings().privacy_version},headers={'Origin':ORIGIN},follow_redirects=False)
    assert response.headers['location']=='/auth/login?error=login_failed'
    assert auth.COOKIE not in response.headers.get('set-cookie','') and c.get('/auth/me').status_code==401


@pytest.mark.parametrize('name',['kakao','naver'])
def test_mock_http_adapter_through_real_db_to_logout(oauth_db,monkeypatch,name):
    import httpx
    sid=uuid4().int % 1000000000 + 1
    def respond(request):
        if request.url.path in ('/oauth/token','/oauth2.0/token'):return httpx.Response(200,json={'token_type':'bearer','access_token':'synthetic'})
        if request.url.path.endswith('access_token_info'):return httpx.Response(200,json={'id':sid,'app_id':1585992,'expires_in':500})
        return httpx.Response(200,json={'id':sid,'kakao_account':{'profile':{'nickname':'가상 회원'}}} if name=='kakao' else {'resultcode':'00','response':{'id':str(sid)}})
    monkeypatch.setattr(p,'_client',lambda:httpx.Client(transport=httpx.MockTransport(respond),follow_redirects=False))
    c=client();state=start(c,name)
    response=c.get('/auth/'+name+'/callback',params={'state':state,'code':'synthetic'},follow_redirects=False)
    assert response.headers['location']=='/auth/signup'
    response=c.get('/auth/signup');csrf=re.search(r'name="csrf" value="([^"]+)"',response.text)[1]
    response=c.post('/auth/signup',data={'csrf':csrf,'terms':'yes','privacy':'yes','terms_version':settings().terms_version,'privacy_version':settings().privacy_version},headers={'Origin':ORIGIN},follow_redirects=False)
    assert response.headers['location']=='/'
    me=c.get('/auth/me');assert me.status_code==200 and me.json()['role']=='member'
    proof=c.get('/auth/csrf').json()['csrf_token']
    assert c.post('/auth/logout',headers={'Origin':ORIGIN,'X-CSRF-Token':proof}).status_code==204
    assert c.get('/auth/me').status_code==401


@pytest.mark.parametrize('name',['kakao','naver'])
@pytest.mark.parametrize('destination',['/','/index.html','/apply.html','/portal/mypage'])
def test_exact_destination_survives_new_signup_and_repeat(oauth_db,monkeypatch,name,destination):
    identity=core.VerifiedIdentity(name,settings().providers[name].identity_scope,uuid4().hex,'가상 회원')
    monkeypatch.setattr(p,'exchange',Mock(return_value=identity))
    c=client();state=start(c,name,destination)
    r=c.get('/auth/'+name+'/callback',params={'state':state,'code':'synthetic'},follow_redirects=False)
    assert r.headers['location']=='/auth/signup'
    page=c.get('/auth/signup');proof=re.search(r'name="csrf" value="([^"]+)"',page.text)[1]
    data={'csrf':proof,'terms':'yes','privacy':'yes','terms_version':settings().terms_version,'privacy_version':settings().privacy_version}
    r=c.post('/auth/signup',data=data,headers={'Origin':ORIGIN},follow_redirects=False)
    assert r.headers['location']==destination and auth.COOKIE in r.headers.get('set-cookie','')
    other=client();state=start(other,name,destination)
    r=other.get('/auth/'+name+'/callback',params={'state':state,'code':'synthetic'},follow_redirects=False)
    assert r.headers['location']==destination
    assert c.get('/auth/me').json()['member_id']==other.get('/auth/me').json()['member_id']


def test_return_migration_reentry_preserves_records(oauth_db):
    cfg=settings();browser='B'*43;state=store.begin(cfg,'kakao',browser,'/apply.html')
    assert login_return_migrate.apply_migration() is False
    assert store.consume_attempt(cfg,'kakao',state,browser)=='/apply.html'


@pytest.mark.parametrize('table',['oauth_attempts','oauth_signups'])
@pytest.mark.parametrize('bad',['//evil.invalid','https://evil.invalid','/auth/login','/apply.html?code=x'])
def test_db_return_constraint_still_rejects_arbitrary_urls(oauth_db,table,bad):
    import psycopg
    cfg=settings();browser='B'*43
    if table=='oauth_attempts':
        token=store.begin(cfg,'kakao',browser,'/portal/mypage');column='state_hash'
    else:
        token=store.stage_signup(cfg,core.VerifiedIdentity('kakao','1585992',uuid4().hex,'가상'),browser,'/portal/mypage');column='ticket_hash'
    # Table and column are hard-coded test selections, not user input.
    with pytest.raises(psycopg.errors.CheckViolation):
        with oauth_db() as db:
            db.execute(f'UPDATE richon.{table} SET return_to=%s WHERE {column}=%s',(bad,core.token_digest(token)))
