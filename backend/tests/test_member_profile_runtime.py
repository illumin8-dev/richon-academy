"""Real registration under exact grants in guarded loopback CI only."""
import os
import pytest
import auth_core as core
import member_profile as profile
import portal_store
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres
from test_oauth_postgres import oauth_db
from test_member_profile_postgres import profile_db, save

pytestmark = pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB') != 'YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


def test_signup_works_with_exact_runtime_grants_and_no_ticket_update(profile_db, monkeypatch):
    import db
    import psycopg
    from psycopg import sql
    import portal_readiness as ready
    with profile_db() as conn:
        assert conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (ready.ROLE,)).fetchone() is None
        conn.execute('CREATE ROLE richon_portal_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
        conn.execute('GRANT USAGE ON SCHEMA richon TO richon_portal_login')
        for table in (*ready.READ, 'member_profiles'):
            conn.execute(sql.SQL('GRANT SELECT ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
        inserts = {**ready.INSERT, 'member_profiles': profile.INSERT_COLUMNS}
        for operation, mapping in (('INSERT', inserts), ('UPDATE', ready.UPDATE)):
            for table, columns in mapping.items():
                statement = sql.SQL('GRANT {} ({}) ON richon.{} TO richon_portal_login').format(
                    sql.SQL(operation), sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier(table))
                conn.execute(statement)
        for table in ready.DELETE:
            conn.execute(sql.SQL('GRANT DELETE ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
    def restricted(_url):
        connection = profile_db()
        connection.autocommit = True
        connection.execute('SET ROLE richon_portal_login')
        connection.autocommit = False
        return connection
    try:
        monkeypatch.setenv('RICHON_TERMS_VERSION', profile.VERSION)
        monkeypatch.setenv('RICHON_PRIVACY_VERSION', profile.VERSION)
        monkeypatch.setattr(db, '_connect', restricted)
        with restricted(None) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                ready.check_cursor(cur)
            assert conn.execute("SELECT has_table_privilege(current_user,'richon.oauth_signups','UPDATE')").fetchone() == (False,)
        mid = save()
        session = core.issue_session(mid)
        assert core.resolve_session(session.token).display_name == '테스트 이름'
        assert portal_store.profile(mid)['registration']['phone'] == '01012345678'
        core.revoke_session(session.token)
        with pytest.raises(core.AuthenticationRequired):
            core.resolve_session(session.token)
        for command in ('DELETE FROM richon.member_profiles WHERE FALSE',
                        'UPDATE richon.member_profiles SET name=name WHERE FALSE',
                        'SELECT * FROM richon.schema_migrations'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with restricted(None) as conn:
                    conn.execute(command)
    finally:
        with profile_db() as conn:
            conn.execute('DROP OWNED BY richon_portal_login')
            conn.execute('DROP ROLE richon_portal_login')
