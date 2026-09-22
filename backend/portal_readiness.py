"""Read-only startup verification for the isolated portal; never performs DDL."""
import os
import sys
import db

ROLE = 'richon_portal_login'
READ = ('members', 'auth_identities', 'member_sessions', 'oauth_attempts',
        'oauth_signups', 'member_order_links', 'courses', 'orders')
INSERT = {
    'members': ('member_id', 'display_name', 'terms_version', 'privacy_version'),
    'auth_identities': ('provider', 'app_id', 'subject', 'member_id'),
    'member_sessions': ('token_hash', 'member_id', 'auth_version', 'role_at_issue', 'expires_at', 'idle_expires_at'),
    'oauth_attempts': ('state_hash', 'browser_hash', 'provider', 'app_id', 'return_to', 'expires_at'),
    'oauth_signups': ('ticket_hash', 'browser_hash', 'provider', 'app_id', 'subject', 'display_name', 'return_to', 'terms_version', 'privacy_version', 'expires_at'),
}
UPDATE = {'members': ('auth_version',),
          'member_sessions': ('last_seen_at', 'idle_expires_at', 'revoked_at'),
          'oauth_attempts': ('consumed_at',)}
DELETE = ('oauth_attempts', 'oauth_signups')


def check_cursor(cur):
    cur.execute("SELECT current_user,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user")
    row = cur.fetchone()
    if not row or row[0] != ROLE or any(row[1:]):
        raise ValueError('portal_role_not_restricted')
    cur.execute("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)")
    if cur.fetchone()[0]:
        raise ValueError('portal_role_membership_not_allowed')
    cur.execute("SELECT has_schema_privilege('richon','USAGE'),has_schema_privilege('richon','CREATE'),has_schema_privilege('public','CREATE'),has_database_privilege(current_database(),'CREATE')")
    if cur.fetchone() != (True, False, False, False):
        raise ValueError('portal_schema_privilege_mismatch')
    for table in READ:
        relation = 'richon.' + table
        cur.execute('SELECT has_table_privilege(%s,\'SELECT\')', (relation,))
        if cur.fetchone() != (True,):
            raise ValueError('portal_read_grant_missing')
        for operation in ('DELETE', 'TRUNCATE', 'TRIGGER', 'REFERENCES'):
            cur.execute('SELECT has_table_privilege(%s,%s)', (relation, operation))
            if cur.fetchone()[0] != (operation == 'DELETE' and table in DELETE):
                raise ValueError('portal_table_grant_mismatch')
        cur.execute("SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped", (relation,))
        columns = [r[0] for r in cur.fetchall()]
        for operation, grants in (('INSERT', INSERT), ('UPDATE', UPDATE)):
            for column in columns:
                cur.execute('SELECT has_column_privilege(%s,%s,%s)', (relation, column, operation))
                if cur.fetchone()[0] != (column in grants.get(table, ())):
                    raise ValueError('portal_column_grant_mismatch')
    for operation in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER'):
        cur.execute('SELECT has_table_privilege(\'richon.schema_migrations\',%s)', (operation,))
        if cur.fetchone()[0]:
            raise ValueError('portal_migration_access_not_allowed')


def verify_database():
    with db._connect(db.database_url()) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='5s'")
            check_cursor(cur)


def main():
    if os.getenv('RICHON_BOOTSTRAP_VERIFY', 'false') == 'true':
        try:
            verify_database()
        except Exception:
            # No DSN, secret, SQL parameters or exception traceback in runtime logs.
            print('PORTAL_DATABASE_CHECK_FAILED', file=sys.stderr)
            return 1
        print('PORTAL_DATABASE_CHECK_PASSED')
    import uvicorn
    uvicorn.run('portal_entry:app', host='0.0.0.0', port=int(os.getenv('PORT', '8080')),
                access_log=False, proxy_headers=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
