"""Withdrawal scrubs optional enrollment PII while preserving course history."""
from uuid import uuid4
import os
import pytest

import account_store as store
import auth_core as core
import monthly_migrate

from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres
from test_oauth_postgres import oauth_db
from test_member_profile_postgres import profile_db
from test_account_postgres import account_db, registered, verified_action
from test_member_profile import cfg

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture(scope='module')
def monthly_account_db(account_db):
    assert monthly_migrate.apply_migration()
    return account_db


def test_paid_learner_can_withdraw_and_enrollment_contact_fields_are_scrubbed(monthly_account_db):
    settings=cfg();identity,mid=registered('naver')
    learner=uuid4()
    with monthly_account_db() as conn:
        conn.execute('''INSERT INTO richon.enrollment_learners
            (learner_id,member_id,name,nickname,email,phone)
            VALUES(%s,%s,%s,%s,%s,%s)''',
            (learner,mid,'유료 수강생','닉네임','learner@example.invalid','01012345678'))
    store.prepare_withdrawal(mid)
    assert verified_action(settings,mid,identity,'withdraw')[:2]==('withdraw',mid)
    assert store.complete_withdraw_provider(settings,mid,identity)==[]
    assert store.finalize_withdrawal(mid)==0
    with monthly_account_db() as conn:
        row=conn.execute('''SELECT member_id,name,nickname,email,phone
                            FROM richon.enrollment_learners WHERE learner_id=%s''',(learner,)).fetchone()
        assert row==(None,'탈퇴 회원',None,None,None)
        assert conn.execute('SELECT status FROM richon.members WHERE member_id=%s',(mid,)).fetchone()==('withdrawn',)
