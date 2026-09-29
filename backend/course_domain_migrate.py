"""Explicit canonical course-domain migration. Never runs at application startup."""
import argparse
import hashlib
from pathlib import Path
import db

VERSION='015_course_run_foundation'
DIRECTORY=Path(__file__).parent/'migrations'
DEPENDENCIES=('001_pending_orders','002_auth_foundation','003_portal_read_models',
              '004_monthly_enrollments','005_manual_registry','009_member_profiles',
              '014_kakao_ci_dedup')

def checksum(name):
    return hashlib.sha256((DIRECTORY/(name+'.sql')).read_bytes()).hexdigest()


def checksum_variant(name, recorded):
    """Classify only known byte-level representations; never expose raw hashes."""
    if not isinstance(recorded,str):
        return 'MISSING'
    raw=(DIRECTORY/(name+'.sql')).read_bytes()
    lf=raw.replace(b'\r\n',b'\n')
    base=lf[:-1] if lf.endswith(b'\n') else lf
    crlf=lf.replace(b'\n',b'\r\n')
    crlf_base=crlf[:-2] if crlf.endswith(b'\r\n') else crlf
    variants=[
        ('EXACT',raw),
        ('LF',lf),
        ('LF_NO_FINAL_NEWLINE',base),
        ('CRLF',crlf),
        ('CRLF_NO_FINAL_NEWLINE',crlf_base),
        ('UTF8_BOM',b'\xef\xbb\xbf'+lf),
        ('UTF8_BOM_CRLF',b'\xef\xbb\xbf'+crlf),
    ]
    for label,data in variants:
        if hashlib.sha256(data).hexdigest()==recorded:
            return label
    return 'UNKNOWN'


def legacy_monthly_compatible(cur):
    """Accept only the known operational DB004 lineage when DB005 is exact.

    This never rewrites schema_migrations. It verifies the monthly schema objects
    that DB015 relies on, while all other dependencies remain exact-checksum.
    """
    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',
                ('005_manual_registry',))
    if cur.fetchone() != (checksum('005_manual_registry'),):
        return False
    cur.execute("""SELECT
        to_regclass('richon.course_month_rules') IS NOT NULL,
        to_regclass('richon.enrollment_learners') IS NOT NULL,
        to_regclass('richon.monthly_enrollments') IS NOT NULL,
        to_regclass('richon.monthly_enrollment_terms') IS NOT NULL,
        to_regprocedure('richon.validate_monthly_term()') IS NOT NULL,
        to_regprocedure('richon.freeze_monthly_course_rule()') IS NOT NULL""")
    if cur.fetchone() != (True,True,True,True,True,True):
        return False
    cur.execute("""SELECT array_agg(attname ORDER BY attnum)
        FROM pg_attribute
        WHERE attrelid='richon.enrollment_learners'::regclass
          AND attnum>0 AND NOT attisdropped""")
    columns=cur.fetchone()[0] or []
    required={'learner_id','member_id','name','nickname','email','phone','created_at'}
    if not required.issubset(set(columns)):
        return False
    cur.execute("""SELECT
        EXISTS (
          SELECT 1 FROM pg_constraint
          WHERE conrelid='richon.enrollment_learners'::regclass
            AND contype='p'
            AND conkey=ARRAY[(SELECT attnum FROM pg_attribute
                              WHERE attrelid='richon.enrollment_learners'::regclass
                                AND attname='learner_id')]::smallint[]
        ),
        EXISTS (
          SELECT 1 FROM pg_constraint
          WHERE conrelid='richon.enrollment_learners'::regclass
            AND contype='f'
            AND confrelid='richon.members'::regclass
        ),
        EXISTS (
          SELECT 1 FROM pg_trigger
          WHERE tgrelid='richon.monthly_enrollment_terms'::regclass
            AND tgname='monthly_term_guard' AND NOT tgisinternal
        ),
        EXISTS (
          SELECT 1 FROM pg_trigger
          WHERE tgrelid='richon.course_month_rules'::regclass
            AND tgname='monthly_rule_guard' AND NOT tgisinternal
        )""")
    return cur.fetchone()==(True,True,True,True)


def dependency_ok(cur, version):
    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
    row=cur.fetchone()
    if row==(checksum(version),):
        return True
    return version=='004_monthly_enrollments' and row is not None and legacy_monthly_compatible(cur)

def apply_migration(*, connection_url=None):
    target=db.database_url() if connection_url is None else connection_url
    with db._connect(target) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='15s'")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute('SELECT pg_advisory_xact_lock(726426,1)')
            for version in DEPENDENCIES:
                if not dependency_ok(cur,version):
                    raise ValueError('dependency_mismatch_'+version)
            cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(VERSION,))
            old=cur.fetchone()
            if old:
                if old!=(checksum(VERSION),):
                    raise ValueError('migration_mismatch')
                return False
            cur.execute((DIRECTORY/(VERSION+'.sql')).read_text())
            cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                        (VERSION,checksum(VERSION)))
    return True

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed course/run/session/enrollment schema.')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        parser.print_help(); raise SystemExit(2)
    try:
        changed=apply_migration()
    except Exception:
        print('FAIL: course-domain migration not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: canonical course domain created.' if changed else
          'PASS: canonical course domain already applied.')
