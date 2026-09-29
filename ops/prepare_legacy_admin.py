"""Owner-only runtime ACL preparation for monthly/manual admin tools.

DB004/005 must already exist with exact checksums. This helper changes privileges only.
It never changes customer rows, schema objects, Cloud Run flags, IAM, secrets or providers.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

from psycopg import sql

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import db
import portal_readiness as ready
import monthly_runtime_hardening_migrate as hardening
import prepare_account_lifecycle as base

MIGRATIONS=ROOT/'backend'/'migrations'
CONFIRM='APPLY_LEGACY_ADMIN_RUNTIME'


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def checksum(version):
    return hashlib.sha256((MIGRATIONS/(version+'.sql')).read_bytes()).hexdigest()


def env_value(service,name):
    values=[item.get('value','') for item in
            service['spec']['template']['spec']['containers'][0].get('env',[])
            if item.get('name')==name]
    need(len(values)<=1,'duplicate_feature_flag')
    return values[0] if values else ''


def validate_source():
    need(subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode==0
         and subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0,
         'tracked_checkout_not_clean')
    for version in ('004_monthly_enrollments','005_manual_registry','017_monthly_runtime_hardening'):
        need((MIGRATIONS/(version+'.sql')).is_file(),'legacy_migration_source_missing')
    need((ROOT/'backend/portal_readiness.py').is_file(),'readiness_missing')


def verify_schema(cur):
    for version in ('004_monthly_enrollments','005_manual_registry'):
        cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
        need(cur.fetchone()==(checksum(version),),version+'_checksum_mismatch')
    cur.execute("""SELECT
        to_regclass('richon.course_month_rules') IS NOT NULL,
        to_regclass('richon.enrollment_learners') IS NOT NULL,
        to_regclass('richon.monthly_enrollments') IS NOT NULL,
        to_regclass('richon.monthly_enrollment_terms') IS NOT NULL,
        to_regclass('richon.manual_learners') IS NOT NULL,
        to_regclass('richon.manual_enrollments') IS NOT NULL,
        to_regclass('richon.manual_terms') IS NOT NULL,
        to_regclass('richon.manual_audit') IS NOT NULL""")
    need(cur.fetchone()==(True,True,True,True,True,True,True,True),'legacy_schema_missing')


def hardening_state(cur):
    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(hardening.VERSION,))
    row=cur.fetchone()
    if row is None:
        return 'ABSENT'
    return 'EXACT' if row==(hardening.checksum(hardening.VERSION),) else 'MISMATCH'


def apply_hardening(cur):
    state=hardening_state(cur)
    if state=='EXACT':
        return False
    need(state=='ABSENT','db017_checksum_mismatch')
    for version in hardening.DEPENDENCIES:
        cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
        need(cur.fetchone()==(hardening.checksum(version),),'dependency_mismatch_'+version)
    cur.execute((hardening.DIRECTORY/(hardening.VERSION+'.sql')).read_text())
    cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                (hardening.VERSION,hardening.checksum(hardening.VERSION)))
    need(hardening_state(cur)=='EXACT','db017_readback_failed')
    return True


def grant_legacy(cur):
    role=sql.Identifier(ready.ROLE)
    dedicated=tuple(dict.fromkeys((*ready.LEGACY_READ,*ready.LEGACY_WRITE_ONLY)))

    for table in dedicated:
        cur.execute(sql.SQL('REVOKE ALL ON richon.{} FROM {}').format(
            sql.Identifier(table),role))

    for table in ready.LEGACY_READ:
        cur.execute(sql.SQL('GRANT SELECT ON richon.{} TO {}').format(
            sql.Identifier(table),role))

    for table,columns in ready.LEGACY_SELECT_COLUMNS.items():
        cur.execute(sql.SQL('GRANT SELECT ({}) ON richon.{} TO {}').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table),role))

    for table,columns in ready.LEGACY_INSERT.items():
        cur.execute(sql.SQL('GRANT INSERT ({}) ON richon.{} TO {}').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table),role))

    for table,columns in ready.LEGACY_UPDATE.items():
        cur.execute(sql.SQL('GRANT UPDATE ({}) ON richon.{} TO {}').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(table),role))

    for table in (*dedicated,'courses','enrollment_learners'):
        cur.execute(sql.SQL('REVOKE DELETE,TRUNCATE,TRIGGER,REFERENCES ON richon.{} FROM {}').format(
            sql.Identifier(table),role))


def configure_expected_runtime():
    os.environ['RICHON_TERMS_VERSION']='member-info-v1'
    os.environ['RICHON_PRIVACY_VERSION']='member-info-v1'
    os.environ['RICHON_ACCOUNT_ENABLED']='true'
    os.environ['RICHON_MARKETING_CONSENT_ENABLED']='true'
    os.environ['RICHON_COURSE_DOMAIN_ENABLED']='true'
    os.environ['RICHON_MONTHLY_ENABLED']='false'
    os.environ['RICHON_MANUAL_ENABLED']='false'


def prepare(owner_url,runtime_url):
    changed017=False
    base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
    base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
    configure_expected_runtime()

    try:
        with db._connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='30s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,4)')
                verify_schema(cur)
                changed017=apply_hardening(cur)
                grant_legacy(cur)
                ready.check_role(cur)
    except (Stop,ValueError):
        raise
    except Exception:
        raise Stop('legacy_grant_transaction_failed') from None

    try:
        with db._connect(runtime_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='10s'")
                ready.check_cursor(cur)
                for table in ready.LEGACY_READ:
                    cur.execute(sql.SQL('SELECT 1 FROM richon.{} LIMIT 0').format(sql.Identifier(table)))
    except (Stop,ValueError):
        raise
    except Exception:
        raise Stop('legacy_runtime_readback_failed') from None
    return changed017


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--diagnose',action='store_true')
    args=parser.parse_args()
    stage='source'
    try:
        validate_source()
        stage='cloud-target'
        project=base.gj('projects','describe',base.PROJECT)
        need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
        _,owner_version=base.secret_ref(base.OWNER_SERVICE,base.OWNER_SECRET)
        portal_service,runtime_version=base.secret_ref(base.PORTAL_SERVICE,base.RUNTIME_SECRET)
        for flag in ('RICHON_ACCOUNT_ENABLED','RICHON_MARKETING_CONSENT_ENABLED','RICHON_COURSE_DOMAIN_ENABLED'):
            need(env_value(portal_service,flag)=='true','required_feature_not_enabled')
        need(env_value(portal_service,'RICHON_MONTHLY_ENABLED')!='true','monthly_already_enabled')
        need(env_value(portal_service,'RICHON_MANUAL_ENABLED')!='true','manual_already_enabled')

        print('TARGET=richon-academy / production Neon / protected portal candidate')
        print('SCOPE=DB017 trigger hardening + DB004/005 runtime ACL / no customer-row changes')
        print('NO_DEPLOY=YES / MONTHLY_MANUAL_REMAIN_OFF=YES / NO_CUSTOMER_ROW_PRINTS=YES')

        stage='secret-access'
        owner_url=base.access(base.OWNER_SECRET,owner_version)
        runtime_url=base.access(base.RUNTIME_SECRET,runtime_version)
        base.validate_dsn(owner_url,base.OWNER_ROLE)
        base.validate_dsn(runtime_url,ready.ROLE)

        base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
        base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
        with db._connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                verify_schema(cur)
                state017=hardening_state(cur)
                need(state017!='MISMATCH','db017_checksum_mismatch')
        print('DB004=EXACT / DB005=EXACT / DB017='+state017)

        if args.diagnose:
            print('DIAGNOSE_ONLY=PASS / NO_DATABASE_CHANGES=YES')
            return 0

        if input('Type '+CONFIRM+' to continue: ').strip()!=CONFIRM:
            print('CANCELLED: no database privilege changes made.')
            return 0

        stage='database-acl'
        changed017=prepare(owner_url,runtime_url)
        print('DB017='+('APPLIED' if changed017 else 'ALREADY_APPLIED'))
        print('LEGACY_ADMIN_RUNTIME_GRANTS=PASS')
        print('RUNTIME_READBACK=PASS')
        print('MONTHLY_MANUAL_FEATURES=OFF')
        print('CUSTOMER_ROWS_CHANGED=NO / SCHEMA_CHANGE=DB017_FUNCTION_ONLY')
        print('CLOUD_RUN_OR_WORKER_CHANGED=NO')
        return 0
    except (Stop,base.Stop,ValueError,Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,(Stop,base.Stop)):
            code=str(exc)
        elif isinstance(exc,ValueError):
            code=str(exc) or 'legacy_readiness_failed'
        else:
            code=type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No secrets printed.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
