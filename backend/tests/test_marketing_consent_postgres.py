"""Advertising-message consent SQL against guarded disposable PostgreSQL only."""
from uuid import uuid4
import os
import pytest

import account_store as account
import auth_core as core
import marketing_consent as marketing
import marketing_consent_migrate as migration
import member_profile as profile
import member_profile_store as registration

from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres
from test_oauth_postgres import oauth_db
from test_member_profile import cfg, data
from test_member_profile_postgres import profile_db, pending
from test_account_postgres import account_db, verified_action

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture(scope='module')
def marketing_db(account_db):
    assert migration.apply_migration()
    return account_db


def signup(consent, monkeypatch, identity=None):
    monkeypatch.setenv(marketing.ENV,'true')
    identity,browser,ticket=pending(identity=identity)
    fields=data()
    if consent:
        fields['marketing']='yes'
    member,target=registration.finish(
        cfg(),ticket,browser,profile.Registration.from_form(fields))
    assert target=='/portal/mypage'
    return identity,member


def test_migration_reentry_schema_and_no_public_access(marketing_db):
    assert migration.apply_migration() is False
    with marketing_db() as conn:
        assert conn.execute(
            "SELECT count(*) FROM richon.schema_migrations WHERE version='011_marketing_consent'"
        ).fetchone()==(1,)
        columns=conn.execute("""SELECT column_name FROM information_schema.columns
            WHERE table_schema='richon' AND table_name='member_marketing_consents'
            ORDER BY ordinal_position""").fetchall()
        assert [row[0] for row in columns]==[
            'member_id','email_enabled','sms_enabled','consent_version',
            'last_consented_at','last_withdrawn_at','updated_at']
        assert conn.execute("""SELECT count(*) FROM pg_class t, LATERAL aclexplode(t.relacl) a
            WHERE t.oid='richon.member_marketing_consents'::regclass AND a.grantee=0""").fetchone()==(0,)


@pytest.mark.parametrize('consent',[False,True])
def test_signup_records_explicit_current_preference(marketing_db,monkeypatch,consent):
    _,member=signup(consent,monkeypatch)
    with marketing_db() as conn:
        row=conn.execute("""SELECT email_enabled,sms_enabled,consent_version,
                                  last_consented_at IS NOT NULL,last_withdrawn_at
                           FROM richon.member_marketing_consents WHERE member_id=%s""",
                         (member,)).fetchone()
        assert row==(consent,consent,marketing.VERSION,consent,None)


def test_duplicate_signup_ticket_never_overwrites_existing_preference(marketing_db,monkeypatch):
    identity,member=signup(True,monkeypatch)
    _,same=signup(False,monkeypatch,identity=identity)
    assert same==member
    with marketing_db() as conn:
        assert conn.execute("""SELECT email_enabled,sms_enabled
            FROM richon.member_marketing_consents WHERE member_id=%s""",(member,)).fetchone()==(True,True)


def test_member_can_opt_in_and_withdraw_without_changing_identity(marketing_db,monkeypatch):
    identity,member=signup(False,monkeypatch)
    account.set_marketing_consent(member,True)
    with marketing_db() as conn:
        first=conn.execute("""SELECT email_enabled,sms_enabled,last_consented_at,last_withdrawn_at
            FROM richon.member_marketing_consents WHERE member_id=%s""",(member,)).fetchone()
        before_identity=conn.execute("""SELECT provider,app_id,subject FROM richon.auth_identities
            WHERE member_id=%s""",(member,)).fetchall()
    assert first[0:2]==(True,True) and first[2] is not None and first[3] is None
    account.set_marketing_consent(member,False)
    with marketing_db() as conn:
        second=conn.execute("""SELECT email_enabled,sms_enabled,last_consented_at,last_withdrawn_at
            FROM richon.member_marketing_consents WHERE member_id=%s""",(member,)).fetchone()
        after_identity=conn.execute("""SELECT provider,app_id,subject FROM richon.auth_identities
            WHERE member_id=%s""",(member,)).fetchall()
    assert second[0:2]==(False,False) and second[2]==first[2] and second[3] is not None
    assert after_identity==before_identity


def test_withdrawal_erases_marketing_preference(marketing_db,monkeypatch):
    identity,member=signup(True,monkeypatch)
    settings=cfg()
    account.prepare_withdrawal(member)
    assert verified_action(settings,member,identity,'withdraw')[:2]==('withdraw',member)
    assert account.complete_withdraw_provider(settings,member,identity)==[]
    assert account.finalize_withdrawal(member)==0
    with marketing_db() as conn:
        assert conn.execute("""SELECT count(*) FROM richon.member_marketing_consents
            WHERE member_id=%s""",(member,)).fetchone()==(0,)


def test_marketing_action_rejects_when_feature_is_off(marketing_db,monkeypatch):
    _,member=signup(False,monkeypatch)
    monkeypatch.setenv(marketing.ENV,'false')
    with pytest.raises(account.AccountActionRejected):
        account.set_marketing_consent(member,True)
