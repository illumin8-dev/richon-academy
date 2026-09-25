"""Exact account-lifecycle runtime grants in guarded disposable PostgreSQL only."""
import os
import secrets
import hashlib
from uuid import uuid4
import pytest

import account_store as account
import auth_core as core
import db
import member_profile as profile
import portal_readiness as ready

from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres
from test_oauth_postgres import oauth_db
from test_member_profile_postgres import profile_db, save
from test_account_postgres import account_db
from test_member_profile import cfg

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture
def restricted_account(account_db,monkeypatch):
    from psycopg import sql
    with account_db() as conn:
        assert conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(ready.ROLE,)).fetchone() is None
        conn.execute('CREATE ROLE richon_portal_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
        conn.execute('GRANT USAGE ON SCHEMA richon TO richon_portal_login')
        for table in (*ready.READ,'member_profiles',*ready.ACCOUNT_READ):
            conn.execute(sql.SQL('GRANT SELECT ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
        inserts=ready.merged_grants({**ready.INSERT,'member_profiles':profile.INSERT_COLUMNS},ready.ACCOUNT_INSERT)
        updates=ready.merged_grants(ready.UPDATE,ready.ACCOUNT_UPDATE)
        for operation,mapping in (('INSERT',inserts),('UPDATE',updates)):
            for table,columns in mapping.items():
                conn.execute(sql.SQL('GRANT {} ({}) ON richon.{} TO richon_portal_login').format(
                    sql.SQL(operation),sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table)))
        for table in tuple(dict.fromkeys((*ready.DELETE,*ready.ACCOUNT_DELETE))):
            conn.execute(sql.SQL('GRANT DELETE ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
    def restricted(_url):
        connection=account_db();connection.autocommit=True
        connection.execute('SET ROLE richon_portal_login');connection.autocommit=False
        return connection
    monkeypatch.setenv('RICHON_TERMS_VERSION',profile.VERSION)
    monkeypatch.setenv('RICHON_PRIVACY_VERSION',profile.VERSION)
    monkeypatch.setenv('RICHON_ACCOUNT_ENABLED','true')
    monkeypatch.setattr(db,'_connect',restricted)
    try:
        with restricted(None) as conn:
            conn.read_only=True
            with conn.cursor() as cur:ready.check_cursor(cur)
        yield restricted
    finally:
        monkeypatch.undo()
        with account_db() as conn:
            conn.execute('DROP OWNED BY richon_portal_login')
            conn.execute('DROP ROLE richon_portal_login')


def add_provider(settings,mid,identity):
    browser=secrets.token_urlsafe(32)
    attempt=account.consume_action_attempt(settings,identity.provider,
        account.begin_action(settings,mid,identity.provider,'link',browser),browser)
    _,_,ticket=account.finish_verified_action(settings,attempt,identity,browser)
    return account.confirm_link(settings,ticket,browser,mid)


def prove(settings,mid,identity,action):
    browser=secrets.token_urlsafe(32)
    attempt=account.consume_action_attempt(settings,identity.provider,
        account.begin_action(settings,mid,identity.provider,action,browser),browser)
    return account.finish_verified_action(settings,attempt,identity,browser)


def test_profile_link_external_unlink_completion_and_withdraw_under_exact_grants(account_db,restricted_account):
    settings=cfg()
    naver=core.VerifiedIdentity('naver',settings.providers['naver'].identity_scope,uuid4().hex,'회원')
    mid=save(naver)
    session=core.issue_session(mid)
    assert account.recent_session(session.token,mid)
    account.update_profile(mid,profile.Registration('권한 테스트','010-2222-3333','runtime@example.invalid',None,None,False,True))
    kakao=core.VerifiedIdentity('kakao',settings.providers['kakao'].identity_scope,uuid4().hex,'회원')
    assert add_provider(settings,mid,kakao)==['kakao','naver']
    assert prove(settings,mid,kakao,'unlink')[:2]==('unlink',mid)
    assert account.complete_unlink(settings,mid,kakao)==['naver']
    # complete_unlink revokes old sessions; create the current member session again.
    session=core.issue_session(mid)
    run=uuid4().hex
    course='runtime-'+run
    order='ord_'+uuid4().hex
    with account_db() as conn:
        conn.execute('INSERT INTO richon.courses(course_id,title,cohort,price_krw,enabled) VALUES(%s,%s,%s,1000,TRUE)',
                     (course,'보존 권한 테스트','테스트'))
        conn.execute('''INSERT INTO richon.orders
            (order_id,idempotency_key,request_fingerprint,course_id,course_title,cohort,amount_krw,
             customer_name,customer_phone,customer_email)
            VALUES(%s,%s,%s,%s,%s,%s,1000,%s,%s,%s)''',
            (order,str(uuid4()),'a'*64,course,'보존 권한 테스트','테스트',
             '실제 보존 이름','01012345678','retain@example.invalid'))
        conn.execute('INSERT INTO richon.member_order_links(order_id,member_id) VALUES(%s,%s)',(order,mid))
    account.prepare_withdrawal(mid)
    assert prove(settings,mid,naver,'withdraw')[:2]==('withdraw',mid)
    assert account.complete_withdraw_provider(settings,mid,naver)==[]
    assert account.finalize_withdrawal(mid)==1
    with pytest.raises(core.AuthenticationRequired):core.resolve_session(session.token)
    with account_db() as conn:
        retained=conn.execute('''SELECT customer_name,customer_phone,customer_email,
                                        expires_at>=order_created_at+interval '5 years'
                                 FROM richon.retained_order_records WHERE order_id=%s''',(order,)).fetchone()
        assert retained==('실제 보존 이름','01012345678','retain@example.invalid',True)
        assert conn.execute('SELECT customer_name,customer_phone,customer_email,request_fingerprint FROM richon.orders WHERE order_id=%s',(order,)).fetchone()==(
            '탈퇴 회원','01000000000','withdrawn@invalid.local',hashlib.sha256(('withdrawn:'+order).encode()).hexdigest())
        assert conn.execute('SELECT count(*) FROM richon.member_order_links WHERE order_id=%s',(order,)).fetchone()==(0,)


@pytest.mark.parametrize('sql',[
    "UPDATE richon.members SET role='admin' WHERE FALSE",
    "DELETE FROM richon.members WHERE FALSE",
    "DELETE FROM richon.orders WHERE FALSE",
    "UPDATE richon.orders SET amount_krw=1 WHERE FALSE",
    "SELECT * FROM richon.schema_migrations",
    "TRUNCATE richon.member_profiles",
    "UPDATE richon.member_profiles SET terms_version=terms_version WHERE FALSE",
    "UPDATE richon.auth_identities SET subject=subject WHERE FALSE",
    "SELECT * FROM richon.retained_order_records",
    "DELETE FROM richon.retained_order_records WHERE FALSE",
])
def test_account_runtime_still_cannot_broaden_privileges(restricted_account,sql):
    import psycopg
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with restricted_account(None) as conn:conn.execute(sql)
