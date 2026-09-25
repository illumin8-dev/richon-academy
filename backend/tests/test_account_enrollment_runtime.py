"""Minimum runtime grants for enrollment scrubbing after withdrawal."""
import os
from uuid import uuid4
import pytest

import member_profile as profile
import portal_readiness as ready

from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres
from test_oauth_postgres import oauth_db
from test_member_profile_postgres import profile_db
from test_account_postgres import account_db
from test_account_enrollment_postgres import monthly_account_db

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


def test_runtime_can_scrub_enrollment_contact_columns_without_reading_them(monthly_account_db,monkeypatch):
    import psycopg
    from psycopg import sql
    learner=uuid4()
    try:
        with monthly_account_db() as conn:
            conn.execute('CREATE ROLE richon_portal_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
            conn.execute('GRANT USAGE ON SCHEMA richon TO richon_portal_login')
            for table in (*ready.READ,'member_profiles',*ready.ACCOUNT_READ):
                conn.execute(sql.SQL('GRANT SELECT ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
            conn.execute('GRANT SELECT (member_id) ON richon.enrollment_learners TO richon_portal_login')
            inserts=ready.merged_grants({**ready.INSERT,'member_profiles':profile.INSERT_COLUMNS},ready.ACCOUNT_INSERT)
            updates=ready.merged_grants(ready.merged_grants(ready.UPDATE,ready.ACCOUNT_UPDATE),ready.ACCOUNT_OPTIONAL_UPDATE)
            for operation,mapping in (('INSERT',inserts),('UPDATE',updates)):
                for table,columns in mapping.items():
                    conn.execute(sql.SQL('GRANT {} ({}) ON richon.{} TO richon_portal_login').format(
                        sql.SQL(operation),sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table)))
            for table in tuple(dict.fromkeys((*ready.DELETE,*ready.ACCOUNT_DELETE))):
                conn.execute(sql.SQL('GRANT DELETE ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
            conn.execute('''INSERT INTO richon.enrollment_learners
                (learner_id,member_id,name,nickname,email,phone)
                VALUES(%s,NULL,%s,%s,%s,%s)''',
                (learner,'권한 테스트','닉네임','runtime@example.invalid','01012345678'))
        monkeypatch.setenv('RICHON_TERMS_VERSION',profile.VERSION)
        monkeypatch.setenv('RICHON_PRIVACY_VERSION',profile.VERSION)
        monkeypatch.setenv('RICHON_ACCOUNT_ENABLED','true')
        with monthly_account_db() as conn:
            with conn.cursor() as cur:
                ready.check_role(cur)
        with monthly_account_db() as conn:
            conn.autocommit=True
            conn.execute('SET ROLE richon_portal_login')
            conn.execute("""UPDATE richon.enrollment_learners
                            SET member_id=NULL,name='탈퇴 회원',nickname=NULL,email=NULL,phone=NULL
                            WHERE member_id IS NULL""")
            assert conn.execute('SELECT member_id FROM richon.enrollment_learners WHERE member_id IS NULL LIMIT 1').fetchone()==(None,)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute('SELECT name FROM richon.enrollment_learners LIMIT 1')
    finally:
        monkeypatch.undo()
        with monthly_account_db() as conn:
            conn.execute('DROP OWNED BY richon_portal_login')
            conn.execute('DROP ROLE IF EXISTS richon_portal_login')
