"""Exact runtime ACL for monthly/manual admin tools on disposable PostgreSQL only."""
from datetime import date
from pathlib import Path
import os
import sys
from uuid import uuid4

import pytest

import monthly_migrate
import manual_migrate
import portal_readiness as ready

from test_portal_bootstrap_postgres import prepared, restricted, runtime_password
from test_auth_postgres import auth_postgres, guarded_target
from test_orders_postgres import postgres

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import prepare_legacy_admin as prep

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture(scope='module')
def legacy_runtime(prepared):
    assert monthly_migrate.apply_migration()
    assert manual_migrate.apply_migration()
    with prepared() as conn:
        with conn.cursor() as cur:
            prep.verify_schema(cur)
            prep.grant_legacy(cur)
    yield prepared


@pytest.fixture
def exact_env(monkeypatch):
    monkeypatch.setenv('RICHON_TERMS_VERSION','internal-test-v1')
    monkeypatch.setenv('RICHON_PRIVACY_VERSION','internal-test-v1')
    monkeypatch.setenv('RICHON_ACCOUNT_ENABLED','false')
    monkeypatch.setenv('RICHON_MARKETING_CONSENT_ENABLED','false')
    monkeypatch.setenv('RICHON_COURSE_DOMAIN_ENABLED','false')
    monkeypatch.setenv('RICHON_MONTHLY_ENABLED','false')
    monkeypatch.setenv('RICHON_MANUAL_ENABLED','false')


def test_prepared_legacy_grants_pass_exact_readiness(legacy_runtime,exact_env):
    with restricted(legacy_runtime) as conn:
        conn.read_only=True
        with conn.cursor() as cur:
            assert ready.legacy_grants_prepared(cur) is True
            ready.check_cursor(cur)


def test_runtime_can_execute_reviewed_manual_write_shape(legacy_runtime,exact_env):
    import psycopg
    run=uuid4().hex
    actor=uuid4()
    learner=uuid4()
    enrollment=uuid4()
    term=uuid4()
    audit=uuid4()
    course='manual-runtime-'+run

    with legacy_runtime() as conn:
        conn.execute("""INSERT INTO richon.members
            (member_id,display_name,terms_version,privacy_version,role)
            VALUES(%s,%s,%s,%s,'admin')""",
            (actor,'가상 관리자','internal-test-v1','internal-test-v1'))

    with restricted(legacy_runtime) as conn:
        conn.execute("""INSERT INTO richon.courses
            (course_id,title,cohort,price_krw,enabled)
            VALUES(%s,%s,%s,1000,FALSE)""",(course,'가상 수동 과정',run))
        conn.execute("""INSERT INTO richon.course_month_rules
            (course_id,start_month,duration_kind,fixed_months)
            VALUES(%s,%s,'monthly',NULL)""",(course,date(2026,10,1)))
        conn.execute("""INSERT INTO richon.enrollment_learners
            (learner_id,name,nickname,email,phone)
            VALUES(%s,%s,%s,%s,%s)""",
            (learner,'가상 수강생','가상 닉네임','legacy@example.invalid','01012345678'))
        conn.execute("""INSERT INTO richon.manual_learners
            (learner_id,original_joined_on,created_by)
            VALUES(%s,%s,%s)""",(learner,date(2026,9,1),actor))
        conn.execute("""INSERT INTO richon.monthly_enrollments
            (enrollment_id,learner_id,course_id) VALUES(%s,%s,%s)""",
            (enrollment,learner,course))
        conn.execute("""INSERT INTO richon.manual_enrollments
            (enrollment_id,created_by) VALUES(%s,%s)""",(enrollment,actor))
        conn.execute("""INSERT INTO richon.monthly_enrollment_terms
            (term_id,enrollment_id,sequence_no,months,grant_state,
             quoted_amount_krw,payment_state,receipt_state,applied_at)
            VALUES(%s,%s,1,3,'pending',1000,'pending','unknown',CURRENT_TIMESTAMP)""",
            (term,enrollment))
        conn.execute("INSERT INTO richon.manual_terms(term_id,created_by) VALUES(%s,%s)",
                     (term,actor))
        conn.execute("""INSERT INTO richon.manual_audit
            (event_id,actor_id,request_id,fingerprint,operation,entity_id,reason,result)
            VALUES(%s,%s,%s,%s,'create',%s,'가상 테스트','{}'::jsonb)""",
            (audit,actor,uuid4(),'a'*64,str(enrollment)))

        conn.execute("UPDATE richon.enrollment_learners SET nickname='수정 닉네임' WHERE learner_id=%s",(learner,))
        conn.execute("""UPDATE richon.monthly_enrollment_terms
            SET months=1,quoted_amount_krw=900 WHERE term_id=%s""",(term,))
        conn.execute("""UPDATE richon.manual_learners
            SET original_joined_on=%s,version=version+1,updated_at=CURRENT_TIMESTAMP
            WHERE learner_id=%s""",(date(2026,8,1),learner))
        conn.execute("""UPDATE richon.manual_enrollments
            SET archived_at=CURRENT_TIMESTAMP,version=version+1,updated_at=CURRENT_TIMESTAMP
            WHERE enrollment_id=%s""",(enrollment,))

        assert conn.execute("SELECT nickname FROM richon.enrollment_learners WHERE learner_id=%s",(learner,)).fetchone()==('수정 닉네임',)
        assert conn.execute("SELECT archived_at IS NOT NULL FROM richon.manual_enrollments WHERE enrollment_id=%s",(enrollment,)).fetchone()==(True,)
        assert conn.execute("SELECT fingerprint,result FROM richon.manual_audit WHERE actor_id=%s",(actor,)).fetchone()[0]=='a'*64

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT operation FROM richon.manual_audit LIMIT 1')
        conn.rollback()


@pytest.mark.parametrize('statement',[
    "DELETE FROM richon.manual_enrollments WHERE FALSE",
    "DELETE FROM richon.monthly_enrollment_terms WHERE FALSE",
    "TRUNCATE richon.manual_audit",
    "UPDATE richon.monthly_enrollments SET course_id=course_id WHERE FALSE",
    "SELECT * FROM richon.schema_migrations",
])
def test_legacy_runtime_cannot_broaden_privileges(legacy_runtime,exact_env,statement):
    import psycopg
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with restricted(legacy_runtime) as conn:
            conn.execute(statement)


def test_helper_source_cannot_deploy_or_mutate_customer_rows():
    source=(Path(__file__).resolve().parents[2]/'ops'/'prepare_legacy_admin.py').read_text()
    assert prep.CONFIRM=='APPLY_LEGACY_ADMIN_GRANTS'
    assert '--set-env-vars' not in source
    assert 'run","deploy' not in source
    assert 'UPDATE richon.' not in source
    assert 'DELETE FROM richon.' not in source
    assert 'MONTHLY_MANUAL_FEATURES=OFF' in source
    assert 'CUSTOMER_ROWS_CHANGED=NO' in source
