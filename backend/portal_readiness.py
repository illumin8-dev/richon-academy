"""Read-only startup verification for the isolated portal; never performs DDL."""
import os
import re
import sys
import db
import member_profile

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
ACCOUNT_READ = ('oauth_account_attempts','oauth_link_confirmations','account_withdrawals',
                'provider_unlink_failures')
ACCOUNT_WRITE_ONLY = ('retained_order_records',)
ACCOUNT_OPTIONAL_WRITE_ONLY = ('enrollment_learners',)
ACCOUNT_SELECT_COLUMNS = {'enrollment_learners': ('member_id',)}
ACCOUNT_OPTIONAL_UPDATE = {
    'enrollment_learners': ('member_id','name','nickname','email','phone'),
}
ACCOUNT_INSERT = {
    'oauth_account_attempts': ('state_hash','browser_hash','member_id','provider','app_id','action','expires_at'),
    'oauth_link_confirmations': ('ticket_hash','browser_hash','member_id','provider','app_id','subject','expires_at'),
    'account_withdrawals': ('member_id','expires_at'),
    'provider_unlink_failures': ('event_id','member_id','provider','safe_code'),
    'retained_order_records': ('order_id','member_id','course_id','course_title','cohort',
                               'amount_krw','currency','status','customer_name','customer_phone',
                               'customer_email','order_created_at','expires_at'),
}
ACCOUNT_UPDATE = {
    'members': ('display_name','status','withdrawn_at'),
    'member_profiles': ('name','phone','email','age_range','gender','consultation_consent'),
    'oauth_account_attempts': ('consumed_at',),
    'orders': ('request_fingerprint','customer_name','customer_phone','customer_email'),
}
ACCOUNT_DELETE = ('auth_identities','member_sessions','member_profiles','member_order_links',
                  'oauth_account_attempts','oauth_link_confirmations','account_withdrawals',
                  'provider_unlink_failures')


def account_enabled():
    return os.getenv('RICHON_ACCOUNT_ENABLED','false') == 'true'


def merged_grants(base, extra):
    result = {table: tuple(columns) for table, columns in base.items()}
    for table, columns in extra.items():
        result[table] = tuple(dict.fromkeys((*result.get(table, ()), *columns)))
    return result


def check_role(cur):
    # Explicit target checks also work for a non-superuser schema owner, without SET ROLE.
    cur.execute("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s", (ROLE,))
    row = cur.fetchone()
    if not row or row[0] != ROLE or any(row[1:]):
        raise ValueError('portal_role_not_restricted')
    cur.execute("SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)", (ROLE,))
    if cur.fetchone()[0]:
        raise ValueError('portal_role_membership_not_allowed')
    cur.execute("SELECT has_schema_privilege(%s,'richon','USAGE'),has_schema_privilege(%s,'richon','CREATE'),has_schema_privilege(%s,'public','CREATE'),has_database_privilege(%s,current_database(),'CREATE')", (ROLE,)*4)
    if cur.fetchone() != (True, False, False, False):
        raise ValueError('portal_schema_privilege_mismatch')
    account = account_enabled()
    profile_active = member_profile.enabled()
    if account and not profile_active:
        raise ValueError('account_requires_member_profile_policy')
    tables = READ + (('member_profiles',) if profile_active else ()) + ((ACCOUNT_READ + ACCOUNT_WRITE_ONLY) if account else ())
    inserts = {**INSERT, **({'member_profiles': member_profile.INSERT_COLUMNS} if profile_active else {})}
    updates = UPDATE
    deletes = DELETE
    write_only = set(ACCOUNT_WRITE_ONLY)
    if account:
        inserts = merged_grants(inserts, ACCOUNT_INSERT)
        updates = merged_grants(UPDATE, ACCOUNT_UPDATE)
        deletes = tuple(dict.fromkeys((*DELETE, *ACCOUNT_DELETE)))
        cur.execute("SELECT to_regclass('richon.enrollment_learners') IS NOT NULL")
        if cur.fetchone()==(True,):
            tables = tables + ACCOUNT_OPTIONAL_WRITE_ONLY
            write_only.update(ACCOUNT_OPTIONAL_WRITE_ONLY)
            updates = merged_grants(updates, ACCOUNT_OPTIONAL_UPDATE)
    for table in tables:
        relation = 'richon.' + table
        cur.execute("SELECT has_table_privilege(%s,%s,'SELECT')", (ROLE,relation))
        expected_select = table not in write_only
        if cur.fetchone() != (expected_select,):
            raise ValueError('portal_read_grant_mismatch')
        for operation in ('DELETE', 'TRUNCATE', 'TRIGGER', 'REFERENCES'):
            cur.execute('SELECT has_table_privilege(%s,%s,%s)', (ROLE,relation,operation))
            if cur.fetchone()[0] != (operation == 'DELETE' and table in deletes):
                raise ValueError('portal_table_grant_mismatch')
        cur.execute("SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped", (relation,))
        columns = [r[0] for r in cur.fetchall()]
        for column in columns:
            cur.execute('SELECT has_column_privilege(%s,%s,%s,%s)', (ROLE,relation,column,'SELECT'))
            expected_column_select = expected_select or column in ACCOUNT_SELECT_COLUMNS.get(table, ())
            if cur.fetchone()[0] != expected_column_select:
                raise ValueError('portal_column_select_grant_mismatch')
        for operation, grants in (('INSERT', inserts), ('UPDATE', updates)):
            for column in columns:
                cur.execute('SELECT has_column_privilege(%s,%s,%s,%s)', (ROLE,relation,column,operation))
                if cur.fetchone()[0] != (column in grants.get(table, ())):
                    raise ValueError('portal_column_grant_mismatch')
    for operation in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'TRIGGER'):
        cur.execute('SELECT has_table_privilege(%s,\'richon.schema_migrations\',%s)', (ROLE,operation))
        if cur.fetchone()[0]:
            raise ValueError('portal_migration_access_not_allowed')


def check_cursor(cur):
    cur.execute('SELECT current_user')
    if cur.fetchone() != (ROLE,):
        raise ValueError('portal_role_not_restricted')
    check_role(cur)


# SQL catalog check, not a query against customer rows or the migration ledger.
RETURN_PATHS = frozenset({'/', '/index.html', '/apply.html', '/portal/mypage',
                         '/portal/admin', '/portal/enrollments', '/portal/manual'})


def constraint_paths(definition):
    """Accept only PostgreSQL's exact text-array membership CHECK expression."""
    if not isinstance(definition, str) or len(definition) > 2048:
        raise ValueError('portal_return_constraint_mismatch')
    compact = re.sub(r"'[^']*'|\s+", lambda m: m[0] if m[0].startswith("'") else '', definition)
    # These are the two built-in representations actually emitted for our
    # text and varchar columns. Do not remove arbitrary casts or SQL clauses.
    templates = (
        ("CHECK((return_to=ANY(ARRAY[", "])))", "text"),
        ("CHECK(((return_to)::text=ANY((ARRAY[", "])::text[])))", "charactervarying"),
    )
    matches = [(compact[len(prefix):-len(suffix)], cast)
               for prefix, suffix, cast in templates
               if compact.startswith(prefix) and compact.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError('portal_return_constraint_mismatch')
    body, cast = matches[0]
    paths = []
    for value in body.split(','):
        atom = re.fullmatch(r"'(/[A-Za-z0-9_./-]*)'::" + cast, value)
        if not atom:
            raise ValueError('portal_return_constraint_mismatch')
        paths.append(atom[1])
    if len(paths) != len(set(paths)):
        raise ValueError('portal_return_constraint_mismatch')
    return frozenset(paths)


def check_return_paths(cur, *, expected_paths=RETURN_PATHS):
    """Refuse to start the new app before migration 008's behavior is present.

    The restricted runtime need not read schema_migrations or gain DDL rights.
    A missing/unvalidated/broadened/extra return_to CHECK fails closed.
    """
    for table in ('oauth_attempts', 'oauth_signups'):
        cur.execute("""
            SELECT c.conname, c.convalidated, c.connoinherit,
                   pg_get_constraintdef(c.oid, false), c.conkey, a.attnum
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attname='return_to'
            WHERE n.nspname='richon' AND t.relname=%s AND c.contype='c'
              AND a.attnum=ANY(c.conkey)
        """, (table,))
        rows = cur.fetchall()
        if len(rows) != 1:
            raise ValueError('portal_return_constraint_mismatch')
        name, validated, noinherit, definition, columns, column = rows[0]
        if (name != table + '_return_to_check' or validated is not True
                or noinherit is not False or list(columns or []) != [column]
                or constraint_paths(definition) != expected_paths):
            raise ValueError('portal_return_constraint_mismatch')


def verify_database():
    with db._connect(db.database_url()) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='5s'")
            check_cursor(cur)
            if os.getenv('RICHON_OAUTH_ENABLED', 'false') == 'true':
                check_return_paths(cur)


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
