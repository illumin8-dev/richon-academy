"""Production course-preparation predecessor guards on disposable PostgreSQL only."""
from pathlib import Path
import os
import sys

import pytest

import auth_migrate
import portal_migrate
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import prepare_course_domain as prep

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture(scope='module')
def predecessor_db(postgres):
    assert auth_migrate.apply_migration()
    assert portal_migrate.apply_migration()

    with postgres() as conn:
        with conn.cursor() as cur:
            assert prep.predecessor_state(cur,'004_monthly_enrollments')=='ABSENT'
            assert prep.predecessor_state(cur,'005_manual_registry')=='ABSENT'

    # Any untracked predecessor object must fail closed instead of being adopted.
    with postgres() as conn:
        conn.execute('CREATE TABLE richon.course_month_rules(dummy integer)')
        with conn.cursor() as cur:
            assert prep.predecessor_state(cur,'004_monthly_enrollments')=='UNTRACKED_PRESENT'
            with pytest.raises(prep.Stop,match='predecessor_004_monthly_enrollments_untracked_present'):
                prep.apply_predecessor(cur,'004_monthly_enrollments')
        conn.rollback()

    with postgres() as conn:
        with conn.cursor() as cur:
            assert prep.apply_predecessor(cur,'004_monthly_enrollments') is True
            assert prep.apply_predecessor(cur,'005_manual_registry') is True
            assert prep.predecessor_state(cur,'004_monthly_enrollments')=='EXACT'
            assert prep.predecessor_state(cur,'005_manual_registry')=='EXACT'

    return postgres


def test_missing_predecessors_are_applied_with_exact_ledger(predecessor_db):
    with predecessor_db() as conn:
        for version in ('004_monthly_enrollments','005_manual_registry'):
            assert conn.execute(
                'SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,)
            ).fetchone()==(prep.domain.checksum(version),)
        for table in (
            'course_month_rules','enrollment_learners','monthly_enrollments',
            'monthly_enrollment_terms','manual_learners','manual_enrollments',
            'manual_terms','manual_audit',
        ):
            assert conn.execute('SELECT to_regclass(%s)',('richon.'+table,)).fetchone()[0] is not None


def test_existing_exact_predecessors_are_idempotent(predecessor_db):
    with predecessor_db() as conn:
        with conn.cursor() as cur:
            assert prep.apply_predecessor(cur,'004_monthly_enrollments') is False
            assert prep.apply_predecessor(cur,'005_manual_registry') is False


def test_missing_ledger_with_existing_tables_is_never_auto_adopted(predecessor_db):
    with predecessor_db() as conn:
        conn.execute("DELETE FROM richon.schema_migrations WHERE version IN ('005_manual_registry','004_monthly_enrollments')")
        with conn.cursor() as cur:
            assert prep.predecessor_state(cur,'004_monthly_enrollments')=='UNTRACKED_PRESENT'
            assert prep.predecessor_state(cur,'005_manual_registry')=='UNTRACKED_PRESENT'
            with pytest.raises(prep.Stop):
                prep.apply_predecessor(cur,'004_monthly_enrollments')
        conn.rollback()
