"""Read-only startup verification for the isolated portal; never performs DDL."""
import os
import re
import sys
import db
import member_profile
import marketing_consent as marketing

ROLE = 'richon_portal_login'
READ = ('members', 'auth_identities', 'member_sessions', 'oauth_attempts',
        'oauth_signups', 'member_order_links', 'courses', 'orders')
PROVIDER_PROFILE_READ = ('member_ci_claims',)
INSERT = {
    'members': ('member_id', 'display_name', 'terms_version', 'privacy_version'),
    'auth_identities': ('provider', 'app_id', 'subject', 'member_id'),
    'member_sessions': ('token_hash', 'member_id', 'auth_version', 'role_at_issue', 'expires_at', 'idle_expires_at'),
    'oauth_attempts': ('state_hash', 'browser_hash', 'provider', 'app_id', 'return_to', 'expires_at'),
    'oauth_signups': ('ticket_hash', 'browser_hash', 'provider', 'app_id', 'subject', 'display_name',
                      'return_to', 'terms_version', 'privacy_version', 'expires_at'),
}
PROVIDER_PROFILE_INSERT = {
    'oauth_signups': ('provider_name','provider_phone','provider_email',
                      'provider_age_range','provider_gender','provider_ci_digest'),
    'member_ci_claims': ('ci_digest','member_id','provider'),
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
    'member_profiles': ('phone','email','age_range','gender','consultation_consent'),
    'oauth_account_attempts': ('consumed_at',),
    'orders': ('request_fingerprint','customer_name','customer_phone','customer_email'),
}
ACCOUNT_DELETE = ('auth_identities','member_sessions','member_profiles','member_ci_claims','member_order_links',
                  'oauth_account_attempts','oauth_link_confirmations','account_withdrawals',
                  'provider_unlink_failures')
MARKETING_READ = ('member_marketing_consents',)
MARKETING_INSERT = {
    'member_marketing_consents': ('member_id','email_enabled','sms_enabled',
                                  'consent_version','last_consented_at'),
}
MARKETING_UPDATE = {
    'member_marketing_consents': ('email_enabled','sms_enabled','consent_version',
                                  'last_consented_at','last_withdrawn_at','updated_at'),
}
MARKETING_DELETE = ('member_marketing_consents',)
COURSE_READ = ('course_programs','course_runs','course_sessions','course_enrollments')
COURSE_WRITE_ONLY = ('course_domain_audit',)
COURSE_SELECT_COLUMNS = {
    'course_domain_audit': ('actor_id','request_id','fingerprint','result'),
    'enrollment_learners': ('learner_id','member_id','name','phone','email','created_at'),
}
COURSE_INSERT = {
    'course_programs': ('program_id','title','description','access_mode','fixed_months'),
    'course_runs': ('run_id','program_id','cohort_label','starts_on','ends_on',
                    'default_access_start','default_access_end','recruit_opens_at',
                    'recruit_closes_at','capacity','status','price_krw'),
    'course_sessions': ('session_id','run_id','sequence_no','title','mentor_name',
                        'starts_at','ends_at','video_url','material_url'),
    'course_enrollments': ('enrollment_id','run_id','learner_id','status','access_start',
                           'access_end','source','note'),
    'course_domain_audit': ('event_id','actor_id','request_id','fingerprint','operation',
                            'entity_id','reason','result'),
    'enrollment_learners': ('learner_id','member_id','name','email','phone'),
}
COURSE_UPDATE = {
    'course_programs': ('title','description','archived_at','version','updated_at'),
    'course_runs': ('cohort_label','recruit_opens_at','recruit_closes_at','capacity',
                    'status','price_krw','archived_at','version','updated_at'),
    'course_sessions': ('title','mentor_name','starts_at','ends_at','video_url',
                        'material_url','cancelled_at','version','updated_at'),
    'course_enrollments': ('status','cancelled_at','suspended_at','version','updated_at'),
}

CALENDAR_READ = ('calendar_events',)
CALENDAR_INSERT = {
    'calendar_events': ('event_id','event_type','title','presenter_name','starts_at','ends_at','is_public'),
}
CALENDAR_UPDATE = {
    'calendar_events': ('event_type','title','presenter_name','starts_at','ends_at','is_public',
                        'cancelled_at','version','updated_at'),
}

LEGACY_READ = ('course_month_rules','monthly_enrollments','monthly_enrollment_terms',
               'manual_learners','manual_enrollments','manual_terms')
LEGACY_WRITE_ONLY = ('manual_audit',)
LEGACY_SELECT_COLUMNS = {
    'manual_audit': ('actor_id','request_id','fingerprint','result'),
    'enrollment_learners': ('learner_id','member_id','name','nickname','phone','email','created_at'),
}
LEGACY_INSERT = {
    'courses': ('course_id','title','cohort','price_krw','enabled'),
    'course_month_rules': ('course_id','start_month','duration_kind','fixed_months'),
    'enrollment_learners': ('learner_id','name','nickname','email','phone'),
    'monthly_enrollments': ('enrollment_id','learner_id','course_id'),
    'monthly_enrollment_terms': ('term_id','enrollment_id','sequence_no','months','grant_state',
        'confirmed_at','confirmation_ref','quoted_amount_krw','payment_state','paid_amount_krw',
        'paid_at','payment_record_ref','receipt_state','receipt_record_ref','applied_at'),
    'manual_learners': ('learner_id','original_joined_on','created_by'),
    'manual_enrollments': ('enrollment_id','created_by'),
    'manual_terms': ('term_id','created_by'),
    'manual_audit': ('event_id','actor_id','request_id','fingerprint','operation','entity_id','reason','result'),
}
LEGACY_UPDATE = {
    'enrollment_learners': ('name','nickname','email','phone'),
    'monthly_enrollment_terms': ('months','grant_state','confirmed_at','confirmation_ref',
        'quoted_amount_krw','payment_state','paid_amount_krw','paid_at','payment_record_ref',
        'receipt_state','receipt_record_ref','applied_at'),
    'manual_learners': ('original_joined_on','version','updated_at'),
    'manual_enrollments': ('version','updated_at','archived_at'),
}


def account_enabled():
    return os.getenv('RICHON_ACCOUNT_ENABLED','false') == 'true'


def marketing_enabled():
    return marketing.enabled()


def course_enabled():
    return os.getenv('RICHON_COURSE_DOMAIN_ENABLED','false') == 'true'


def monthly_enabled():
    return os.getenv('RICHON_MONTHLY_ENABLED','false') == 'true'


def manual_enabled():
    return os.getenv('RICHON_MANUAL_ENABLED','false') == 'true'


def merged_grants(base, extra):
    result = {table: tuple(columns) for table, columns in base.items()}
    for table, columns in extra.items():
        result[table] = tuple(dict.fromkeys((*result.get(table, ()), *columns)))
    return result


def account_grants_prepared(cur):
    """Recognize only the reviewed DB010 runtime grant profile marker.

    This does not enable account routes. It only lets a new revision start
    between owner-run privilege preparation and a later feature-gate change.
    Exact privilege checks below still reject missing or broader grants.
    """
    cur.execute("SELECT to_regclass('richon.retained_order_records') IS NOT NULL")
    if cur.fetchone() != (True,):
        return False
    cur.execute("""SELECT has_column_privilege(
        %s,'richon.retained_order_records','order_id','INSERT')""",(ROLE,))
    return cur.fetchone() == (True,)


def marketing_grants_prepared(cur):
    cur.execute("SELECT to_regclass('richon.member_marketing_consents') IS NOT NULL")
    if cur.fetchone() != (True,):
        return False
    cur.execute("""SELECT has_column_privilege(
        %s,'richon.member_marketing_consents','member_id','INSERT')""",(ROLE,))
    return cur.fetchone() == (True,)


def course_grants_prepared(cur):
    cur.execute("SELECT to_regclass('richon.course_domain_audit') IS NOT NULL")
    if cur.fetchone() != (True,):
        return False
    cur.execute("""SELECT
        has_column_privilege(%s,'richon.course_programs','program_id','INSERT'),
        has_column_privilege(%s,'richon.course_domain_audit','event_id','INSERT')""",
        (ROLE,ROLE))
    return cur.fetchone()==(True,True)


def calendar_grants_prepared(cur):
    cur.execute("SELECT to_regclass('richon.calendar_events') IS NOT NULL")
    if cur.fetchone()!=(True,): return False
    cur.execute("""SELECT
        has_table_privilege(%s,'richon.calendar_events','SELECT'),
        has_column_privilege(%s,'richon.calendar_events','event_id','INSERT')""",(ROLE,ROLE))
    return cur.fetchone()==(True,True)


def legacy_grants_prepared(cur):
    cur.execute("""SELECT
        to_regclass('richon.monthly_enrollments') IS NOT NULL,
        to_regclass('richon.manual_audit') IS NOT NULL""")
    if cur.fetchone() != (True,True):
        return False
    cur.execute("""SELECT
        has_table_privilege(%s,'richon.monthly_enrollments','SELECT'),
        has_column_privilege(%s,'richon.manual_audit','event_id','INSERT'),
        has_column_privilege(%s,'richon.enrollment_learners','nickname','SELECT')""",
        (ROLE,ROLE,ROLE))
    return cur.fetchone()==(True,True,True)


def provider_profile_schema_ready(cur):
    cur.execute("""SELECT count(*) FROM pg_attribute
        WHERE attrelid='richon.oauth_signups'::regclass AND attnum>0 AND NOT attisdropped
          AND attname=ANY(ARRAY['provider_name','provider_phone','provider_email',
                                'provider_age_range','provider_gender','provider_ci_digest'])""")
    if cur.fetchone()!=(6,):
        return False
    cur.execute("SELECT to_regclass('richon.member_ci_claims') IS NOT NULL")
    return cur.fetchone()==(True,)


def provider_profile_grants_prepared(cur):
    if not provider_profile_schema_ready(cur):
        return False
    cur.execute("""SELECT
        has_column_privilege(%s,'richon.oauth_signups','provider_name','INSERT'),
        has_column_privilege(%s,'richon.oauth_signups','provider_phone','INSERT'),
        has_column_privilege(%s,'richon.oauth_signups','provider_email','INSERT'),
        has_column_privilege(%s,'richon.oauth_signups','provider_age_range','INSERT'),
        has_column_privilege(%s,'richon.oauth_signups','provider_gender','INSERT'),
        has_column_privilege(%s,'richon.oauth_signups','provider_ci_digest','INSERT'),
        has_column_privilege(%s,'richon.member_ci_claims','ci_digest','INSERT'),
        has_column_privilege(%s,'richon.member_ci_claims','member_id','INSERT'),
        has_column_privilege(%s,'richon.member_ci_claims','provider','INSERT')""",
        (ROLE,ROLE,ROLE,ROLE,ROLE,ROLE,ROLE,ROLE,ROLE))
    return cur.fetchone()==(True,True,True,True,True,True,True,True,True)


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
    marketing_active = marketing_enabled()
    course_active = course_enabled()
    calendar_active = course_active
    monthly_active = monthly_enabled()
    manual_active = manual_enabled()
    if account and not profile_active:
        raise ValueError('account_requires_member_profile_policy')
    if marketing_active and not profile_active:
        raise ValueError('marketing_requires_member_profile_policy')
    if course_active and not account:
        raise ValueError('course_requires_account_feature')
    if manual_active and not monthly_active:
        raise ValueError('manual_requires_monthly_feature')
    if profile_active and not provider_profile_schema_ready(cur):
        raise ValueError('provider_profile_schema_required')
    provider_profile_grants = profile_active or provider_profile_grants_prepared(cur)
    account_grants = account or account_grants_prepared(cur)
    marketing_grants = marketing_active or marketing_grants_prepared(cur)
    course_grants = course_active or course_grants_prepared(cur)
    calendar_grants = calendar_active or calendar_grants_prepared(cur)
    legacy_grants = monthly_active or manual_active or legacy_grants_prepared(cur)
    tables = READ + (PROVIDER_PROFILE_READ if provider_profile_grants else ()) + (('member_profiles',) if profile_active else ()) + ((ACCOUNT_READ + ACCOUNT_WRITE_ONLY) if account_grants else ()) + (MARKETING_READ if marketing_grants else ()) + ((COURSE_READ + COURSE_WRITE_ONLY) if course_grants else ()) + (CALENDAR_READ if calendar_grants else ()) + ((LEGACY_READ + LEGACY_WRITE_ONLY) if legacy_grants else ())
    inserts = {**INSERT, **({'member_profiles': member_profile.INSERT_COLUMNS} if profile_active else {})}
    select_columns = {table: tuple(columns) for table,columns in ACCOUNT_SELECT_COLUMNS.items()}
    if provider_profile_grants:
        inserts = merged_grants(inserts, PROVIDER_PROFILE_INSERT)
    updates = UPDATE
    deletes = DELETE
    write_only = set(ACCOUNT_WRITE_ONLY)
    if account_grants:
        inserts = merged_grants(inserts, ACCOUNT_INSERT)
        updates = merged_grants(UPDATE, ACCOUNT_UPDATE)
        deletes = tuple(dict.fromkeys((*DELETE, *ACCOUNT_DELETE)))
        cur.execute("SELECT to_regclass('richon.enrollment_learners') IS NOT NULL")
        if cur.fetchone()==(True,):
            tables = tables + ACCOUNT_OPTIONAL_WRITE_ONLY
            write_only.update(ACCOUNT_OPTIONAL_WRITE_ONLY)
            updates = merged_grants(updates, ACCOUNT_OPTIONAL_UPDATE)
    if marketing_grants:
        inserts = merged_grants(inserts, MARKETING_INSERT)
        updates = merged_grants(updates, MARKETING_UPDATE)
        deletes = tuple(dict.fromkeys((*deletes, *MARKETING_DELETE)))
    if course_grants:
        inserts = merged_grants(inserts, COURSE_INSERT)
        updates = merged_grants(updates, COURSE_UPDATE)
        tables = tuple(dict.fromkeys((*tables, 'enrollment_learners')))
        write_only.update(COURSE_WRITE_ONLY)
        write_only.add('enrollment_learners')
        for table,columns in COURSE_SELECT_COLUMNS.items():
            select_columns[table] = tuple(dict.fromkeys((*select_columns.get(table,()), *columns)))
    if calendar_grants:
        inserts = merged_grants(inserts, CALENDAR_INSERT)
        updates = merged_grants(updates, CALENDAR_UPDATE)
    if legacy_grants:
        inserts = merged_grants(inserts, LEGACY_INSERT)
        updates = merged_grants(updates, LEGACY_UPDATE)
        tables = tuple(dict.fromkeys((*tables, 'enrollment_learners')))
        write_only.update(LEGACY_WRITE_ONLY)
        write_only.add('enrollment_learners')
        for table,columns in LEGACY_SELECT_COLUMNS.items():
            select_columns[table] = tuple(dict.fromkeys((*select_columns.get(table,()), *columns)))
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
            expected_column_select = expected_select or column in select_columns.get(table, ())
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
