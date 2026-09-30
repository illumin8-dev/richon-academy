"""Exact marketing-consent runtime grants in guarded disposable PostgreSQL only."""
import os
import pytest
from psycopg import sql

import account_store as account
import db
import marketing_consent as marketing
import member_profile as profile
import portal_readiness as ready

from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres
from test_oauth_postgres import oauth_db
from test_member_profile_postgres import profile_db
from test_account_postgres import account_db
from test_account_runtime import restricted_account
from test_marketing_consent_postgres import marketing_db, signup

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


def grant_marketing(conn):
    role=sql.Identifier(ready.ROLE)
    for table in ready.MARKETING_READ:
        conn.execute(sql.SQL('GRANT SELECT ON richon.{} TO {}').format(sql.Identifier(table),role))
    for operation,mapping in (('INSERT',ready.MARKETING_INSERT),('UPDATE',ready.MARKETING_UPDATE)):
        for table,columns in mapping.items():
            conn.execute(sql.SQL('GRANT {} ({}) ON richon.{} TO {}').format(
                sql.SQL(operation),sql.SQL(',').join(map(sql.Identifier,columns)),
                sql.Identifier(table),role))
    for table in ready.MARKETING_DELETE:
        conn.execute(sql.SQL('GRANT DELETE ON richon.{} TO {}').format(sql.Identifier(table),role))


def test_signup_edit_readiness_and_denied_broad_writes_under_exact_grants(
        marketing_db,restricted_account,monkeypatch):
    with marketing_db() as conn:
        grant_marketing(conn)
    monkeypatch.setenv(marketing.ENV,'true')
    with restricted_account(None) as conn:
        conn.read_only=True
        with conn.cursor() as cur:
            assert ready.marketing_grants_prepared(cur) is True
            ready.check_cursor(cur)
    _,member=signup(True,monkeypatch)
    account.set_marketing_consent(member,False)
    with restricted_account(None) as conn:
        assert conn.execute("""SELECT email_enabled,sms_enabled FROM richon.member_marketing_consents
            WHERE member_id=%s""",(member,)).fetchone()==(False,False)
    import psycopg
    for statement in (
        "TRUNCATE richon.member_marketing_consents",
        "UPDATE richon.member_marketing_consents SET member_id=member_id WHERE FALSE",
        "UPDATE richon.member_marketing_consents SET updated_at=updated_at, member_id=member_id WHERE FALSE",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with restricted_account(None) as conn:
                conn.execute(statement)


def test_marketing_gate_fails_closed_without_exact_grant(marketing_db,restricted_account,monkeypatch):
    with marketing_db() as conn:
        grant_marketing(conn)
        conn.execute('REVOKE DELETE ON richon.member_marketing_consents FROM richon_portal_login')
    monkeypatch.setenv(marketing.ENV,'true')
    with pytest.raises(ValueError,match='portal_table_grant_mismatch'):
        with restricted_account(None) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                ready.check_cursor(cur)
