"""Account lifecycle SQL against guarded disposable loopback PostgreSQL only."""
from uuid import uuid4
import os
import secrets
import pytest

import account_migrate
import account_store as store
import auth_core as core
import member_profile as profile
import orders

from test_member_profile import cfg
from test_member_profile_postgres import profile_db, save

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture(scope='module')
def account_db(profile_db):
    assert account_migrate.apply_migration()
    return profile_db


def registered(provider='naver'):
    settings=cfg()
    identity=core.VerifiedIdentity(provider,settings.providers[provider].identity_scope,uuid4().hex,'회원')
    return identity,save(identity)


def link_identity(settings,member,identity):
    browser=secrets.token_urlsafe(32)
    state=store.begin_action(settings,member,identity.provider,'link',browser)
    attempt=store.consume_action_attempt(settings,identity.provider,state,browser)
    action,linked,ticket=store.finish_verified_action(settings,attempt,identity,browser)
    assert (action,linked)==('link',member)
    return store.confirm_link(settings,ticket,browser,member)


def verified_action(settings,member,identity,action):
    browser=secrets.token_urlsafe(32)
    state=store.begin_action(settings,member,identity.provider,action,browser)
    attempt=store.consume_action_attempt(settings,identity.provider,state,browser)
    return store.finish_verified_action(settings,attempt,identity,browser)


def test_migration_reentry_and_schema(account_db):
    assert account_migrate.apply_migration() is False
    with account_db() as conn:
        assert conn.execute("SELECT count(*) FROM richon.schema_migrations WHERE version='010_account_lifecycle'").fetchone()==(1,)
        names=conn.execute("""SELECT to_regclass('richon.oauth_account_attempts'),to_regclass('richon.oauth_link_confirmations'),
          to_regclass('richon.account_withdrawals'),to_regclass('richon.provider_unlink_failures'),
          to_regclass('richon.retained_order_records')""").fetchone()
        assert names==('richon.oauth_account_attempts','richon.oauth_link_confirmations','richon.account_withdrawals',
                       'richon.provider_unlink_failures','richon.retained_order_records')


def test_profile_update_changes_profile_not_identity(account_db):
    identity,mid=registered()
    with account_db() as conn:
        before=conn.execute('SELECT provider,app_id,subject FROM richon.auth_identities WHERE member_id=%s',(mid,)).fetchall()
    update=profile.Registration('바뀐 이름','010-9876-5432','changed@example.invalid','40-49','female',True,True)
    store.update_profile(mid,update)
    with account_db() as conn:
        assert conn.execute('SELECT name,phone,email,age_range,gender,consultation_consent FROM richon.member_profiles WHERE member_id=%s',(mid,)).fetchone()==(
            '바뀐 이름','01098765432','changed@example.invalid','40-49','female',True)
        assert conn.execute('SELECT display_name FROM richon.members WHERE member_id=%s',(mid,)).fetchone()==('바뀐 이름',)
        assert conn.execute('SELECT provider,app_id,subject FROM richon.auth_identities WHERE member_id=%s',(mid,)).fetchall()==before


def test_link_requires_confirmation_then_same_member_has_both(account_db):
    settings=cfg();_,mid=registered('naver')
    new_identity=core.VerifiedIdentity('kakao',settings.providers['kakao'].identity_scope,uuid4().hex,'회원')
    browser=secrets.token_urlsafe(32)
    state=store.begin_action(settings,mid,'kakao','link',browser)
    attempt=store.consume_action_attempt(settings,'kakao',state,browser)
    action,member,ticket=store.finish_verified_action(settings,attempt,new_identity,browser)
    assert (action,member)==('link',mid) and store.pending_link(settings,ticket,browser,mid)=='kakao'
    with account_db() as conn:
        assert conn.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id=%s',(mid,)).fetchone()==(1,)
    assert store.confirm_link(settings,ticket,browser,mid)==['kakao','naver']


def test_identity_owned_by_other_member_cannot_be_linked(account_db):
    settings=cfg();other_identity,other=registered('kakao');_,target=registered('naver')
    browser=secrets.token_urlsafe(32)
    attempt=store.consume_action_attempt(settings,'kakao',
        store.begin_action(settings,target,'kakao','link',browser),browser)
    with pytest.raises(store.IdentityInUse):
        store.finish_verified_action(settings,attempt,other_identity,browser)
    with account_db() as conn:
        assert conn.execute('SELECT member_id FROM richon.auth_identities WHERE provider=%s AND app_id=%s AND subject=%s',
                            (other_identity.provider,other_identity.app_id,other_identity.subject)).fetchone()==(other,)


def test_reauth_requires_same_existing_identity_and_freshness_uses_session_age(account_db):
    settings=cfg();identity,mid=registered('naver');session=core.issue_session(mid)
    assert store.recent_session(session.token,mid)
    with account_db() as conn:
        conn.execute("UPDATE richon.member_sessions SET created_at=CURRENT_TIMESTAMP-interval '20 minutes' WHERE token_hash=%s",
                     (core.token_digest(session.token),))
    assert not store.recent_session(session.token,mid)
    assert verified_action(settings,mid,identity,'reauth')[:2]==('reauth',mid)
    wrong=core.VerifiedIdentity('naver',identity.app_id,uuid4().hex,'회원')
    browser=secrets.token_urlsafe(32)
    attempt=store.consume_action_attempt(settings,'naver',
        store.begin_action(settings,mid,'naver','reauth',browser),browser)
    with pytest.raises(store.ProviderNotLinked):
        store.finish_verified_action(settings,attempt,wrong,browser)


def test_provider_unlink_requires_provider_proof_and_never_removes_last_method(account_db):
    settings=cfg();naver,mid=registered('naver')
    with pytest.raises(store.LastLoginMethod):
        store.begin_action(settings,mid,'naver','unlink',secrets.token_urlsafe(32))
    kakao=core.VerifiedIdentity('kakao',settings.providers['kakao'].identity_scope,uuid4().hex,'회원')
    assert link_identity(settings,mid,kakao)==['kakao','naver']
    assert verified_action(settings,mid,kakao,'unlink')[:2]==('unlink',mid)
    store.record_unlink_failure(mid,'kakao')
    assert store.unlink_failure_pending(mid)
    assert store.complete_unlink(settings,mid,kakao)==['naver']
    assert not store.unlink_failure_pending(mid)
    with account_db() as conn:
        assert conn.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id=%s',(mid,)).fetchone()==(1,)


def test_withdrawal_erases_account_auth_profile_after_all_provider_unlinks_and_retains_transaction(account_db):
    settings=cfg();identity,mid=registered('naver');session=core.issue_session(mid)
    run=uuid4().hex;course='account-'+run
    with account_db() as conn:
        conn.execute('INSERT INTO richon.courses(course_id,title,cohort,price_krw,enabled) VALUES(%s,%s,%s,1000,TRUE)',
                     (course,'탈퇴 보존 테스트','테스트'))
    request=orders.OrderRequest(course_id=course,customer_name='거래 기록 이름',
        customer_phone='01000000000',customer_email='retained@example.invalid')
    order=orders.create_pending_order(request,uuid4()).order
    with account_db() as conn:
        conn.execute('INSERT INTO richon.member_order_links(order_id,member_id) VALUES(%s,%s)',(order.order_id,mid))
    store.prepare_withdrawal(mid)
    assert store.withdrawal_status(mid,settings)==['naver']
    assert verified_action(settings,mid,identity,'withdraw')[:2]==('withdraw',mid)
    assert store.complete_withdraw_provider(settings,mid,identity)==[]
    assert store.finalize_withdrawal(mid)==1
    with pytest.raises(core.AuthenticationRequired):
        core.resolve_session(session.token)
    with account_db() as conn:
        assert conn.execute('SELECT status,withdrawn_at IS NOT NULL,display_name FROM richon.members WHERE member_id=%s',(mid,)).fetchone()==(
            'withdrawn',True,'탈퇴 회원')
        assert conn.execute('SELECT count(*) FROM richon.member_profiles WHERE member_id=%s',(mid,)).fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id=%s',(mid,)).fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM richon.member_sessions WHERE member_id=%s',(mid,)).fetchone()==(0,)
        assert conn.execute('SELECT member_id FROM richon.member_order_links WHERE order_id=%s',(order.order_id,)).fetchone() is None
        retained=conn.execute('''SELECT member_id,customer_name,customer_phone,customer_email,
                                        expires_at>=order_created_at+interval '5 years'
                                 FROM richon.retained_order_records WHERE order_id=%s''',(order.order_id,)).fetchone()
        assert retained==(mid,'거래 기록 이름','01000000000','retained@example.invalid',True)
        operational=conn.execute('''SELECT customer_name,customer_phone,customer_email,request_fingerprint
                                    FROM richon.orders WHERE order_id=%s''',(order.order_id,)).fetchone()
        assert operational[:3]==('탈퇴 회원','01000000000','withdrawn@invalid.local')
        assert operational[3]!=request.fingerprint()
    new_mid=save(identity)
    assert new_mid!=mid


def test_withdrawal_can_be_cancelled_before_provider_unlink(account_db):
    _,mid=registered('naver');settings=cfg()
    store.prepare_withdrawal(mid)
    assert store.withdrawal_status(mid,settings)==['naver']
    store.cancel_withdrawal(mid)
    assert store.withdrawal_status(mid,settings) is None
    with account_db() as conn:
        assert conn.execute('SELECT status FROM richon.members WHERE member_id=%s',(mid,)).fetchone()==('active',)
