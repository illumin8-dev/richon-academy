"""Real SQL only against the guarded, disposable loopback richon_ci database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import os
import pytest
import auth_core as core
import consultation_privacy as privacy
import consultation_privacy_migrate as migration
import member_profile
import portal_store
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres
from test_oauth_postgres import oauth_db
from test_member_profile_postgres import profile_db, save, pending
from test_consultation_privacy import activate

pytestmark = pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB') != 'YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture(scope='module')
def privacy_db(profile_db):
    # Prove that applying the additional column does not rewrite old consent.
    mid = save(consultation='yes', age_range='30-39', gender='female')
    with profile_db() as conn:
        before = conn.execute('SELECT * FROM richon.member_profiles WHERE member_id=%s', (mid,)).fetchone()
    assert migration.apply_migration()
    with profile_db() as conn:
        after = conn.execute('SELECT * FROM richon.member_profiles WHERE member_id=%s', (mid,)).fetchone()
    assert after == before + (None,)
    return profile_db


@pytest.fixture
def enabled(monkeypatch):
    activate(monkeypatch)


def consented():
    identity, _, _ = pending()
    mid = save(identity, consultation='yes', age_range='30-39', gender='female')
    return mid, core.issue_session(mid).token, identity


def test_migration_reentry_and_catalog(privacy_db, enabled):
    assert migration.apply_migration() is False
    with privacy_db() as conn:
        assert conn.execute("SELECT count(*) FROM richon.schema_migrations WHERE version=%s", (migration.VERSION,)).fetchone() == (1,)
        with conn.cursor() as cur: privacy.check_schema(cur)


def test_only_own_optional_values_change_and_signup_cannot_restore(privacy_db, enabled):
    a, token, identity = consented()
    b, _, _ = consented()
    # Snapshot every existing table except the four intended profile columns.
    tables = ('members', 'auth_identities', 'member_sessions', 'orders', 'member_order_links', 'courses')
    with privacy_db() as conn:
        snapshots = {t: conn.execute('SELECT * FROM richon.' + t + ' ORDER BY 1').fetchall() for t in tables}
        before = conn.execute('SELECT name,phone,email,terms_version,privacy_version,consented_at FROM richon.member_profiles WHERE member_id=%s', (a,)).fetchone()
        other = conn.execute('SELECT * FROM richon.member_profiles WHERE member_id=%s', (b,)).fetchone()
    result = privacy.withdraw(token)
    assert result.consultation_consent is False and result.withdrawn_at is not None
    with privacy_db() as conn:
        row = conn.execute('SELECT age_range,gender,consultation_consent,consultation_withdrawn_at FROM richon.member_profiles WHERE member_id=%s', (a,)).fetchone()
        assert row == (None, None, False, result.withdrawn_at)
        assert conn.execute('SELECT name,phone,email,terms_version,privacy_version,consented_at FROM richon.member_profiles WHERE member_id=%s', (a,)).fetchone() == before
        assert conn.execute('SELECT * FROM richon.member_profiles WHERE member_id=%s', (b,)).fetchone() == other
        for t in tables:
            assert conn.execute('SELECT * FROM richon.' + t + ' ORDER BY 1').fetchall() == snapshots[t]
    assert privacy.withdraw(token) == result
    assert save(identity, consultation='yes', age_range='50-59', gender='male') == a
    assert privacy.withdraw(token) == result
    assert core.resolve_session(token).member_id == a
    assert portal_store.profile(a)['registration']['consultation_consent'] is False


def test_never_consented_does_not_fabricate_timestamp(privacy_db, enabled):
    mid = save(); token = core.issue_session(mid).token
    assert privacy.withdraw(token).withdrawn_at is None
    assert privacy.withdraw(token).withdrawn_at is None


def test_different_sessions_concurrent_withdrawal_preserves_first_timestamp(privacy_db, enabled):
    mid, _, _ = consented()
    tokens = [core.issue_session(mid).token for _ in range(4)]
    barrier = Barrier(4)
    def call(token):
        barrier.wait(timeout=10)
        return privacy.withdraw(token).withdrawn_at
    with ThreadPoolExecutor(max_workers=4) as pool:
        stamps = list(pool.map(call, tokens))
    assert stamps[0] is not None and len(set(stamps)) == 1


@pytest.mark.parametrize('case', ['revoked', 'expired', 'idle', 'disabled', 'version', 'role', 'missing_profile'])
def test_invalid_current_session_cannot_write(privacy_db, enabled, case):
    mid, token, _ = consented()
    with privacy_db() as conn:
        if case == 'revoked': conn.execute('UPDATE richon.member_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE token_hash=%s', (core.token_digest(token),))
        elif case == 'expired': conn.execute("UPDATE richon.member_sessions SET created_at=CURRENT_TIMESTAMP-interval '1 day',expires_at=CURRENT_TIMESTAMP-interval '1 second',idle_expires_at=CURRENT_TIMESTAMP-interval '2 seconds' WHERE token_hash=%s", (core.token_digest(token),))
        elif case == 'idle': conn.execute("UPDATE richon.member_sessions SET idle_expires_at=CURRENT_TIMESTAMP-interval '1 second' WHERE token_hash=%s", (core.token_digest(token),))
        elif case == 'disabled': conn.execute("UPDATE richon.members SET status='disabled' WHERE member_id=%s", (mid,))
        elif case == 'version': conn.execute('UPDATE richon.members SET auth_version=auth_version+1 WHERE member_id=%s', (mid,))
        elif case == 'role': conn.execute("UPDATE richon.members SET role='admin' WHERE member_id=%s", (mid,))
        else: conn.execute('DELETE FROM richon.member_profiles WHERE member_id=%s', (mid,))
    with pytest.raises(core.AuthenticationRequired): privacy.withdraw(token)
    with privacy_db() as conn:
        row = conn.execute('SELECT age_range,gender,consultation_consent,consultation_withdrawn_at FROM richon.member_profiles WHERE member_id=%s', (mid,)).fetchone()
        assert row is None if case == 'missing_profile' else row == ('30-39', 'female', True, None)


def test_commit_failure_rolls_back_erasure_and_timestamp(privacy_db, enabled):
    import psycopg
    mid, token, _ = consented()
    with privacy_db() as conn:
        conn.execute("CREATE FUNCTION richon.test_privacy_commit_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic failure'; END; $$")
        conn.execute('CREATE CONSTRAINT TRIGGER test_privacy_commit_fail AFTER UPDATE ON richon.member_profiles DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION richon.test_privacy_commit_fail()')
    try:
        with pytest.raises(psycopg.errors.RaiseException): privacy.withdraw(token)
        with privacy_db() as conn:
            assert conn.execute('SELECT age_range,gender,consultation_consent,consultation_withdrawn_at FROM richon.member_profiles WHERE member_id=%s', (mid,)).fetchone() == ('30-39', 'female', True, None)
    finally:
        with privacy_db() as conn:
            conn.execute('DROP TRIGGER test_privacy_commit_fail ON richon.member_profiles')
            conn.execute('DROP FUNCTION richon.test_privacy_commit_fail()')
    assert privacy.withdraw(token).withdrawn_at is not None


def test_runtime_grants_are_narrow_and_fail_closed(privacy_db, enabled, monkeypatch):
    import db
    import psycopg
    from psycopg import sql
    import portal_readiness as ready
    mid, token, _ = consented()
    with privacy_db() as conn:
        assert conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (ready.ROLE,)).fetchone() is None
        conn.execute('CREATE ROLE richon_portal_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
        conn.execute('GRANT USAGE ON SCHEMA richon TO richon_portal_login')
        for table in (*ready.READ, 'member_profiles'):
            conn.execute(sql.SQL('GRANT SELECT ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
        inserts = {**ready.INSERT, 'member_profiles': member_profile.INSERT_COLUMNS}
        for operation, mapping in (('INSERT', inserts), ('UPDATE', ready.UPDATE)):
            for table, columns in mapping.items():
                conn.execute(sql.SQL('GRANT {} ({}) ON richon.{} TO richon_portal_login').format(
                    sql.SQL(operation), sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier(table)))
        for table in ready.DELETE:
            conn.execute(sql.SQL('GRANT DELETE ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
    def restricted(_url):
        conn = privacy_db(); conn.autocommit = True
        conn.execute('SET ROLE richon_portal_login'); conn.autocommit = False
        return conn
    try:
        with restricted(None) as conn, conn.cursor() as cur:
            with pytest.raises(ValueError, match='portal_column_grant_mismatch'): ready.check_cursor(cur)
        with privacy_db() as conn:
            conn.execute('GRANT UPDATE (age_range,gender,consultation_consent,consultation_withdrawn_at) ON richon.member_profiles TO richon_portal_login')
        monkeypatch.setattr(db, '_connect', restricted)
        with restricted(None) as conn, conn.cursor() as cur: ready.check_cursor(cur)
        assert privacy.withdraw(token).withdrawn_at is not None
        assert core.resolve_session(token).member_id == mid
        for command in ('DELETE FROM richon.member_profiles WHERE FALSE',
                        'UPDATE richon.member_profiles SET name=name WHERE FALSE',
                        'UPDATE richon.member_profiles SET phone=phone WHERE FALSE',
                        'UPDATE richon.member_profiles SET email=email WHERE FALSE',
                        'UPDATE richon.member_profiles SET consented_at=consented_at WHERE FALSE',
                        'SELECT * FROM richon.schema_migrations'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with restricted(None) as conn: conn.execute(command)
        with privacy_db() as conn: conn.execute('GRANT UPDATE (name) ON richon.member_profiles TO richon_portal_login')
        with restricted(None) as conn, conn.cursor() as cur:
            with pytest.raises(ValueError, match='portal_column_grant_mismatch'): ready.check_cursor(cur)
    finally:
        with privacy_db() as conn:
            conn.execute('DROP OWNED BY richon_portal_login')
            conn.execute('DROP ROLE richon_portal_login')


def test_missing_timestamp_column_fails_without_creating_it(privacy_db, enabled):
    with privacy_db() as conn: conn.execute('ALTER TABLE richon.member_profiles RENAME COLUMN consultation_withdrawn_at TO temporary_hidden_stamp')
    try:
        with privacy_db() as conn, conn.cursor() as cur:
            with pytest.raises(ValueError, match='schema_missing'): privacy.check_schema(cur)
    finally:
        with privacy_db() as conn: conn.execute('ALTER TABLE richon.member_profiles RENAME COLUMN temporary_hidden_stamp TO consultation_withdrawn_at')
