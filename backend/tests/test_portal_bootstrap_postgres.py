"""Real SQL against opt-in, empty loopback CI database ONLY; no Neon/GCP calls."""
from pathlib import Path
import os
import secrets
import sys
from uuid import uuid4
import pytest
import auth_core as core
import portal_store
import db
import portal_readiness as ready
from test_orders_postgres import postgres
from test_auth_postgres import auth_postgres, guarded_target, CONSENT

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import prepare_portal as p

pytestmark=pytest.mark.skipif(os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),reason='Needs disposable loopback richon_ci')


@pytest.fixture(scope='module')
def runtime_password():
    return secrets.token_urlsafe(32)


@pytest.fixture(scope='module')
def prepared(auth_postgres, runtime_password):
    connect=auth_postgres
    with connect() as conn:
        assert conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(ready.ROLE,)).fetchone() is None
    created=False
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                changed=p.schema(cur)
                assert changed==['003_portal_read_models','007_oauth_handoff']
                # Match the observed Neon logging baseline in this disposable
                # CI transaction only. Production code merely checks settings.
                for name, value in (
                    ('log_statement', 'none'), ('log_min_duration_statement', '-1'),
                    ('log_min_duration_sample', '-1'), ('log_transaction_sample_rate', '0'),
                    ('log_min_error_statement', 'panic'), ('log_error_verbosity', 'terse'),
                    ('log_parameter_max_length_on_error', '0'),
                ):
                    cur.execute('SELECT set_config(%s,%s,true)', (name, value))
                p.grant_runtime(cur,runtime_password,conn)
                # Cleanup must happen before the same transaction/pooled session
                # is released, not merely when a physical backend disconnects.
                cur.execute("SELECT to_regprocedure('pg_temp.richon_create_portal_login(text)')")
                assert cur.fetchone() == (None,)
        created=True
        yield connect
    finally:
        if created:
            with connect() as conn:
                # Fixture proved this new role did not exist; localhost CI only.
                conn.execute('DROP OWNED BY richon_portal_login')
                conn.execute('DROP ROLE richon_portal_login')


def restricted(connect):
    c=connect()
    c.autocommit=True
    c.execute('SET ROLE richon_portal_login')
    c.autocommit=False
    return c


def test_schema_reentry_and_no_prices_migration(prepared):
    with prepared() as conn:
        with conn.cursor() as cur:
            assert p.schema(cur)==[]
        assert conn.execute("SELECT count(*) FROM richon.schema_migrations WHERE version IN ('004_monthly_enrollments','005_manual_registry','006_pricing_notes')").fetchone()==(0,)


def test_actual_restricted_role_passes_readonly_startup(prepared):
    with restricted(prepared) as conn:
        conn.read_only=True
        with conn.cursor() as cur:ready.check_cursor(cur)


def test_signup_session_portal_and_logout_under_minimal_grants(prepared,monkeypatch):
    monkeypatch.setattr(db,'_connect',lambda _url:restricted(prepared))
    identity=core.VerifiedIdentity('kakao','1585992',uuid4().hex,'가상 회원')
    member=core.register_verified_identity(identity,CONSENT)
    session=core.issue_session(member)
    assert core.resolve_session(session.token).role=='member'
    assert portal_store.profile(member)['member_id']==member
    assert portal_store.own_orders(member,20,0)['items']==[]
    core.revoke_all_sessions(member)
    with pytest.raises(core.AuthenticationRequired):core.resolve_session(session.token)


@pytest.mark.parametrize('sql',[
    "UPDATE richon.members SET role='admin' WHERE FALSE",
    "DELETE FROM richon.members WHERE FALSE",
    "UPDATE richon.orders SET amount_krw=1 WHERE FALSE",
    "DELETE FROM richon.orders WHERE FALSE",
    "INSERT INTO richon.member_order_links(order_id,member_id) SELECT 'never',NULL::uuid WHERE FALSE",
    "SELECT * FROM richon.schema_migrations",
    "CREATE TABLE richon.bootstrap_forbidden (id integer)",
])
def test_forbidden_privileges(prepared,sql):
    import psycopg
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with restricted(prepared) as conn:conn.execute(sql)


def test_broader_privilege_fails_readiness_and_is_rolled_back(prepared):
    with pytest.raises(ValueError,match='column_grant'):
        with prepared() as conn:
            conn.execute('GRANT UPDATE(role) ON richon.members TO richon_portal_login')
            conn.execute('SET LOCAL ROLE richon_portal_login')
            with conn.cursor() as cur:ready.check_cursor(cur)
    with restricted(prepared) as conn:
        with conn.cursor() as cur:ready.check_cursor(cur)


def test_new_migrations_rollback_together_on_failure(auth_postgres,prepared):
    # Roll back a ledger corruption deliberately; no weakening the checksum guard.
    with pytest.raises(p.Stop,match='schema_checksum'):
        with prepared() as conn:
            conn.execute("UPDATE richon.schema_migrations SET checksum=repeat('a',64) WHERE version='007_oauth_handoff'")
            with conn.cursor() as cur:p.schema(cur)
    with prepared() as conn:
        with conn.cursor() as cur:assert p.schema(cur)==[]


def test_grant_check_needs_no_set_role_privilege(prepared):
    import psycopg
    from psycopg import sql
    owner='bootstrap_ci_owner_'+uuid4().hex[:12]
    with prepared() as conn:
        with conn.transaction():
            conn.execute(sql.SQL('CREATE ROLE {} CREATEROLE NOSUPERUSER').format(sql.Identifier(owner)))
            conn.execute(sql.SQL('GRANT richon_portal_login TO {} WITH ADMIN TRUE, SET FALSE, INHERIT FALSE').format(sql.Identifier(owner)))
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA richon TO {} WITH GRANT OPTION').format(sql.Identifier(owner)))
            conn.execute(sql.SQL('GRANT ALL ON ALL TABLES IN SCHEMA richon TO {} WITH GRANT OPTION').format(sql.Identifier(owner)))
            conn.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(owner)))
            assert conn.execute("SELECT pg_has_role(current_user,'richon_portal_login','SET')").fetchone()==(False,)
            with conn.cursor() as cur:p.grant_runtime(cur,'unused-existing-role',conn)
            raise psycopg.Rollback()
        assert conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(owner,)).fetchone() is None


def test_runtime_password_authentication_over_loopback(prepared, runtime_password):
    import psycopg
    # guarded_target has already rejected non-loopback / non-richon_ci targets.
    with psycopg.connect(os.environ['RICHON_TEST_DATABASE_URL'],
                         user=ready.ROLE, password=runtime_password) as conn:
        conn.read_only=True
        with conn.cursor() as cur:ready.check_cursor(cur)


def test_credential_helper_is_not_a_persistent_database_function(prepared):
    with prepared() as conn:
        assert conn.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('richon','public') AND p.proname='richon_create_portal_login'").fetchone()==(0,)


def test_managed_role_reentry_does_not_create_or_rotate_password(prepared, monkeypatch):
    from unittest.mock import Mock
    create=Mock(side_effect=AssertionError('existing role must not rotate'))
    monkeypatch.setattr(p,'create_runtime_role',create)
    with prepared() as conn:
        with conn.cursor() as cur:p.grant_runtime(cur,'unused-existing-role',conn)
    create.assert_not_called()
