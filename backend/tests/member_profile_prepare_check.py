"""Execute the exact owner SQL in an empty GitHub CI PostgreSQL service only.

The neondb name/owner deliberately match the production guard. Host and initial
emptiness guards prevent use against Neon. No production credentials are read.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
from threading import Barrier
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / 'backend'))
import portal_readiness as ready
import member_profile

SCRIPT = (ROOT / 'ops/prepare_member_profiles.sql').read_text()
MIGRATIONS = ROOT / 'backend/migrations'
URL = os.environ.get('RICHON_TEST_DATABASE_URL', '')
VERSIONS = ('001_pending_orders','002_auth_foundation','003_portal_read_models',
            '007_oauth_handoff','008_login_return_paths')
TABLES = ready.READ
OWNER = 'neondb_owner'
ROLE = ready.ROLE
MID = '00000000-0000-4000-8000-000000000001'
created_schema = False
created_roles = []
passed = 0


def connect():
    return psycopg.connect(URL, connect_timeout=5, prepare_threshold=None)


def run_script(conn):
    cur = conn.execute(SCRIPT)
    last = None
    while True:
        if cur.description:
            last = cur.fetchone()
        if not cur.nextset():
            break
    assert last == (True,) * 6, ('readback_not_all_true', last)


def absent():
    with connect() as conn:
        assert conn.execute("SELECT to_regclass('richon.member_profiles')").fetchone() == (None,)
        assert conn.execute("SELECT count(*) FROM richon.schema_migrations WHERE version='009_member_profiles'").fetchone() == (0,)


def setup():
    global created_schema
    with connect() as conn:
        if created_schema:
            conn.execute('DROP SCHEMA richon CASCADE')
        conn.execute('CREATE SCHEMA richon')
        conn.execute('REVOKE ALL ON SCHEMA richon FROM PUBLIC')
        conn.execute('CREATE TABLE richon.schema_migrations(version text PRIMARY KEY, checksum char(64) NOT NULL, applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        conn.execute('REVOKE ALL ON richon.schema_migrations FROM PUBLIC')
        for version in VERSIONS:
            source = (MIGRATIONS/(version+'.sql')).read_bytes()
            conn.execute(source.decode())
            conn.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                         (version,hashlib.sha256(source).hexdigest()))
        conn.execute('GRANT USAGE ON SCHEMA richon TO richon_portal_login')
        for table in ready.READ:
            conn.execute(sql.SQL('GRANT SELECT ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
        for operation, mapping in (('INSERT', ready.INSERT),('UPDATE',ready.UPDATE)):
            for table,columns in mapping.items():
                conn.execute(sql.SQL('GRANT {} ({}) ON richon.{} TO richon_portal_login').format(
                    sql.SQL(operation),sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table)))
        for table in ready.DELETE:
            conn.execute(sql.SQL('GRANT DELETE ON richon.{} TO richon_portal_login').format(sql.Identifier(table)))
        conn.execute("INSERT INTO richon.members(member_id,display_name,terms_version,privacy_version) VALUES(%s,'합성 회원','internal-test-v1','internal-test-v1')", (MID,))
        conn.execute("INSERT INTO richon.auth_identities(provider,app_id,subject,member_id) VALUES('naver','ci-app','synthetic-subject',%s)", (MID,))
        conn.execute("INSERT INTO richon.courses(course_id,title,price_krw) VALUES('ci-course','시험 강의',1000)")
        conn.execute("INSERT INTO richon.orders(order_id,idempotency_key,request_fingerprint,course_id,course_title,amount_krw,customer_name,customer_phone,customer_email) VALUES(%s,%s,%s,'ci-course','시험 강의',1000,'시험','01000000000','test@example.invalid')", ('ord_'+'a'*32, uuid4(), 'b'*64))
        conn.execute('INSERT INTO richon.member_order_links(order_id,member_id) VALUES(%s,%s)',('ord_'+'a'*32,MID))
        conn.execute("INSERT INTO richon.member_sessions(token_hash,member_id,auth_version,role_at_issue,expires_at,idle_expires_at) VALUES(%s,%s,1,'member',CURRENT_TIMESTAMP+interval '1 day',CURRENT_TIMESTAMP+interval '1 hour')",('c'*64,MID))
    created_schema = True


def fingerprint():
    with connect() as conn:
        rows = {table: conn.execute(sql.SQL('SELECT * FROM richon.{} ORDER BY 1').format(sql.Identifier(table))).fetchall() for table in TABLES}
        acls = conn.execute("SELECT relname,relowner,relacl FROM pg_class WHERE relnamespace='richon'::regnamespace AND relkind='r' AND relname<> 'member_profiles' ORDER BY relname").fetchall()
        return rows,acls


def expect_failure(label, operation, expected):
    global passed
    try:
        operation()
    except psycopg.Error as exc:
        assert expected in str(exc), (label,'unexpected_sql_error',exc.sqlstate)
    else:
        raise AssertionError(label+': expected failure')
    passed += 1
    print('PASS:',label)


def execute():
    with connect() as conn:
        run_script(conn)


def main():
    global passed
    target = urlsplit(URL)
    assert os.getenv('GITHUB_ACTIONS') == 'true'
    assert os.getenv('RICHON_EMPTY_TEST_DB') == 'YES'
    assert not os.getenv('DATABASE_URL')
    assert target.hostname in ('127.0.0.1','localhost','::1') and target.path == '/neondb'
    assert target.username == OWNER
    with connect() as conn:
        assert conn.execute('SELECT current_database(),current_user').fetchone() == ('neondb',OWNER)
        assert conn.execute("SELECT to_regnamespace('richon')").fetchone() == (None,)
        assert conn.execute('SELECT count(*) FROM pg_roles WHERE rolname IN (%s,%s)',(ROLE,'ci_unexpected_reader')).fetchone() == (0,)
        conn.execute('CREATE ROLE richon_portal_login NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
        conn.execute('CREATE ROLE ci_unexpected_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT')
    created_roles.extend([ROLE,'ci_unexpected_reader'])
    canonical=(MIGRATIONS/'009_member_profiles.sql').read_text()
    embedded=SCRIPT.split('-- BEGIN CANONICAL 009 (bytes between markers match the approved migration)\n',1)[1].split('-- END CANONICAL 009',1)[0]
    assert embedded==canonical
    for version in (*VERSIONS[:2],*VERSIONS[3:],'009_member_profiles'):
        assert hashlib.sha256((MIGRATIONS/(version+'.sql')).read_bytes()).hexdigest() in SCRIPT
    passed+=1;print('PASS: exact approved migration bytes and dependency hashes')
    setup()
    before=fingerprint()
    execute()
    assert fingerprint()==before
    with connect() as conn:
        assert conn.execute('SELECT count(*) FROM richon.member_profiles').fetchone()==(0,)
        conn.execute('SET ROLE richon_portal_login')
        with conn.cursor() as cur:
            os.environ.update(RICHON_TERMS_VERSION='internal-test-v1',RICHON_PRIVACY_VERSION='internal-test-v1')
            ready.check_cursor(cur)
            os.environ.update(RICHON_TERMS_VERSION=member_profile.VERSION,RICHON_PRIVACY_VERSION=member_profile.VERSION)
            ready.check_cursor(cur);ready.check_return_paths(cur)
    passed+=1;print('PASS: create, exact grants, no existing row or ACL changes, old/new readiness')
    before=fingerprint()
    expect_failure('repeat refuses without adopting/changing existing data',execute,'ALREADY_PRESENT')
    assert fingerprint()==before
    # Actual restricted role can use only the insert columns; rollback synthetic insert.
    conn=connect()
    try:
        conn.execute('SET ROLE richon_portal_login')
        conn.execute("INSERT INTO richon.member_profiles(member_id,name,phone,email,age_range,gender,consultation_consent,over14_confirmed,terms_version,privacy_version) VALUES(%s,'합성 회원','01012345678','test@example.invalid','30-39','female',TRUE,TRUE,'member-info-v1','member-info-v1')",(MID,))
        assert conn.execute('SELECT name,consented_at IS NOT NULL FROM richon.member_profiles WHERE member_id=%s',(MID,)).fetchone()==('합성 회원',True)
    finally:
        conn.rollback();conn.close()
    passed+=1;print('PASS: restricted role real INSERT and SELECT; timestamp supplied by database')
    for command in ('UPDATE richon.member_profiles SET name=name WHERE FALSE',
                    'DELETE FROM richon.member_profiles WHERE FALSE',
                    'TRUNCATE richon.member_profiles',
                    'SELECT * FROM richon.schema_migrations',
                    'ALTER TABLE richon.member_profiles ADD COLUMN forbidden text',
                    'INSERT INTO richon.member_profiles(consented_at) SELECT CURRENT_TIMESTAMP WHERE FALSE'):
        def attempt():
            with connect() as conn:
                conn.execute('SET ROLE richon_portal_login');conn.execute(command)
        expect_failure('restricted operation denied: '+command.split()[0],attempt,'permission denied' if not command.startswith('ALTER') else 'must be owner')
    setup()
    def wrong_owner():
        with connect() as conn:
            conn.execute('SET ROLE richon_portal_login');run_script(conn)
    expect_failure('wrong owner fails before writes',wrong_owner,'WRONG_DATABASE_OR_OWNER');absent()
    with connect() as conn:
        conn.execute("UPDATE richon.schema_migrations SET checksum=repeat('0',64) WHERE version='008_login_return_paths'")
    expect_failure('wrong dependency checksum fails before writes',execute,'DEPENDENCY_CHECKSUM_MISMATCH');absent()
    setup()
    with connect() as conn:
        conn.execute("INSERT INTO richon.schema_migrations(version,checksum) VALUES('009_member_profiles',repeat('0',64))")
    expect_failure('ledger without table is not overwritten',execute,'ALREADY_PRESENT')
    setup()
    with connect() as conn:conn.execute('CREATE TABLE richon.member_profiles(unrelated integer)')
    expect_failure('unrecorded table is not adopted',execute,'ALREADY_PRESENT')
    setup()
    with connect() as conn:conn.execute('ALTER ROLE richon_portal_login CREATEDB')
    try:
        expect_failure('elevated runtime is rejected',execute,'RUNTIME_ROLE_NOT_RESTRICTED');absent()
    finally:
        with connect() as conn:conn.execute('ALTER ROLE richon_portal_login NOCREATEDB')
    # A grant mismatch discovered AFTER creation and ledger write must roll back all.
    with connect() as conn:conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA richon GRANT SELECT ON TABLES TO ci_unexpected_reader')
    try:
        expect_failure('unexpected default ACL rolls back DDL, grant and ledger',execute,'UNEXPECTED_DEFAULT_GRANT');absent()
    finally:
        with connect() as conn:conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA richon REVOKE SELECT ON TABLES FROM ci_unexpected_reader')
    before=fingerprint()
    barrier=Barrier(2)
    def parallel():
        barrier.wait(timeout=10)
        try:
            execute();return 'ready'
        except psycopg.Error as exc:
            assert 'OTHER_MIGRATION_RUNNING' in str(exc) or 'ALREADY_PRESENT' in str(exc)
            return 'stopped'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:parallel(),range(2)))
    assert sorted(outcomes)==['ready','stopped'] and fingerprint()==before
    passed+=1;print('PASS: concurrent runs create exactly once')
    with connect() as conn:
        assert conn.execute("SELECT count(*) FROM richon.schema_migrations WHERE version='009_member_profiles'").fetchone()==(1,)
    print(f'PASS: {passed} checks. Exact SQL, disposable loopback PostgreSQL only. No live Neon or GCP.')


if __name__=='__main__':
    try:
        main()
    finally:
        if created_schema:
            with connect() as conn:conn.execute('DROP SCHEMA richon CASCADE')
        if created_roles:
            with connect() as conn:
                for role in reversed(created_roles):
                    conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
                    conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
