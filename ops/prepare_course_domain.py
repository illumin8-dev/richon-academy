"""Owner-run production preparation for canonical course management (DB015/016 + exact grants).

This script applies only the reviewed canonical course/run/session/enrollment schema,
its entitlement extension, and minimum privileges for richon_portal_login.
It never deploys Cloud Run, changes feature flags, calls providers, or prints
database URLs, passwords, tokens, or customer rows.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import db
import course_domain_migrate as domain
import course_entitlement_migrate as entitlements
import portal_readiness as ready
import prepare_account_lifecycle as base

MINIMUM_SOURCE='185128166d439eb36ed1b8ea993bb4e531e6bde8'
CONFIRM='APPLY_DB015_016'


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def validate_source():
    need(base.command(['git','merge-base','--is-ancestor',MINIMUM_SOURCE,'HEAD'])=='',
         'required_course_source_not_present')
    need(subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode==0
         and subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0,
         'tracked_checkout_not_clean')
    for migration in (domain,entitlements):
        need((migration.DIRECTORY/(migration.VERSION+'.sql')).is_file(),
             'course_migration_missing')
    need((ROOT/'backend/portal_readiness.py').is_file(),'readiness_missing')


def env_value(service,name):
    values=[item.get('value','') for item in
            service['spec']['template']['spec']['containers'][0].get('env',[])
            if item.get('name')==name]
    need(len(values)<=1,'duplicate_feature_flag')
    return values[0] if values else ''


def grant_course(cur):
    from psycopg import sql
    role=sql.Identifier(ready.ROLE)

    # New course tables have no legacy runtime contract, so normalize them first.
    for table in (*ready.COURSE_READ,*ready.COURSE_WRITE_ONLY):
        relation=sql.SQL('richon.{}').format(sql.Identifier(table))
        cur.execute(sql.SQL('REVOKE ALL ON {} FROM {}').format(relation,role))

    for table in ready.COURSE_READ:
        cur.execute(sql.SQL('GRANT SELECT ON richon.{} TO {}').format(
            sql.Identifier(table),role))

    for table,columns in ready.COURSE_SELECT_COLUMNS.items():
        cur.execute(sql.SQL('GRANT SELECT ({}) ON richon.{} TO {}').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),
            sql.Identifier(table),role))

    for table,columns in ready.COURSE_INSERT.items():
        cur.execute(sql.SQL('GRANT INSERT ({}) ON richon.{} TO {}').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),
            sql.Identifier(table),role))

    for table,columns in ready.COURSE_UPDATE.items():
        cur.execute(sql.SQL('GRANT UPDATE ({}) ON richon.{} TO {}').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),
            sql.Identifier(table),role))

    # No course-domain route requires destructive table operations.
    for table in (*ready.COURSE_READ,*ready.COURSE_WRITE_ONLY,'enrollment_learners'):
        cur.execute(sql.SQL('REVOKE DELETE,TRUNCATE,TRIGGER,REFERENCES ON richon.{} FROM {}').format(
            sql.Identifier(table),role))


def migration_checksum(migration):
    path=migration.DIRECTORY/(migration.VERSION+'.sql')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_one(cur,migration):
    for version in migration.DEPENDENCIES:
        cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
        need(cur.fetchone()==(migration.checksum(version),),
             'dependency_mismatch_'+version)
    checksum=migration_checksum(migration)
    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',
                (migration.VERSION,))
    old=cur.fetchone()
    if old is None:
        cur.execute((migration.DIRECTORY/(migration.VERSION+'.sql')).read_text())
        cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                    (migration.VERSION,checksum))
        return True
    need(old==(checksum,),migration.VERSION+'_checksum_mismatch')
    return False


def apply(owner_url,runtime_url):
    base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
    base.diagnose_connection(runtime_url,ready.ROLE,'runtime')

    changed015=False
    changed016=False
    try:
        with db._connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='45s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,3)')
                changed015=apply_one(cur,domain)
                changed016=apply_one(cur,entitlements)
                grant_course(cur)
                ready.check_role(cur)
    except (Stop,ValueError):
        raise
    except Exception:
        raise Stop('course_database_transaction_failed') from None

    try:
        with db._connect(runtime_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='10s'")
                ready.check_cursor(cur)
                for table in ready.COURSE_READ:
                    cur.execute('SELECT 1 FROM richon.'+table+' LIMIT 0')
    except (Stop,ValueError):
        raise
    except Exception:
        raise Stop('course_runtime_readback_failed') from None

    try:
        with db._connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                for migration in (domain,entitlements):
                    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',
                                (migration.VERSION,))
                    need(cur.fetchone()==(migration_checksum(migration),),
                         migration.VERSION+'_readback_failed')
                cur.execute("""SELECT
                    to_regclass('richon.course_programs') IS NOT NULL,
                    to_regclass('richon.course_runs') IS NOT NULL,
                    to_regclass('richon.course_sessions') IS NOT NULL,
                    to_regclass('richon.course_enrollments') IS NOT NULL,
                    to_regclass('richon.course_domain_audit') IS NOT NULL""")
                need(cur.fetchone()==(True,True,True,True,True),
                     'course_tables_missing')
    except Stop:
        raise
    except Exception:
        raise Stop('course_owner_final_readback_failed') from None
    return changed015,changed016


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--diagnose',action='store_true',
                        help='Read-only production target checks. Does not apply DB015/016 or grants.')
    args=parser.parse_args()
    stage='source'
    try:
        validate_source()

        stage='cloud-target'
        project=base.gj('projects','describe',base.PROJECT)
        need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
        _,owner_version=base.secret_ref(base.OWNER_SERVICE,base.OWNER_SECRET)
        portal_service,runtime_version=base.secret_ref(base.PORTAL_SERVICE,base.RUNTIME_SECRET)
        need(env_value(portal_service,'RICHON_ACCOUNT_ENABLED')=='true',
             'account_feature_not_enabled')
        need(env_value(portal_service,'RICHON_MARKETING_CONSENT_ENABLED')=='true',
             'marketing_feature_not_enabled')
        need(env_value(portal_service,'RICHON_COURSE_DOMAIN_ENABLED')!='true',
             'course_feature_already_enabled')

        print('TARGET=richon-academy / production Neon / protected portal candidate')
        print('SCOPE=DB015+DB016 + exact richon_portal_login course grants + readback')
        print('NO_DEPLOY=YES / COURSE_FEATURE_REMAINS_OFF=YES / NO_CUSTOMER_ROW_PRINTS=YES')

        stage='secret-access'
        owner_url=base.access(base.OWNER_SECRET,owner_version)
        runtime_url=base.access(base.RUNTIME_SECRET,runtime_version)
        base.validate_dsn(owner_url,base.OWNER_ROLE)
        base.validate_dsn(runtime_url,ready.ROLE)

        if args.diagnose:
            base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
            base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
            print('DIAGNOSE_ONLY=PASS / NO_DATABASE_CHANGES=YES')
            return 0

        if input('Type '+CONFIRM+' to continue: ').strip()!=CONFIRM:
            print('CANCELLED: no database changes made.')
            return 0

        # Match the currently approved account/marketing runtime contract while
        # validating prepared course grants; this does not change Cloud Run env.
        os.environ['RICHON_TERMS_VERSION']='member-info-v1'
        os.environ['RICHON_PRIVACY_VERSION']='member-info-v1'
        os.environ['RICHON_ACCOUNT_ENABLED']='true'
        os.environ['RICHON_MARKETING_CONSENT_ENABLED']='true'
        os.environ.pop('RICHON_COURSE_DOMAIN_ENABLED',None)

        stage='database'
        changed015,changed016=apply(owner_url,runtime_url)
        print('DB015='+('APPLIED' if changed015 else 'ALREADY_APPLIED'))
        print('DB016='+('APPLIED' if changed016 else 'ALREADY_APPLIED'))
        print('RUNTIME_MINIMUM_PRIVILEGES=PASS')
        print('RUNTIME_READBACK=PASS')
        print('COURSE_FEATURE=OFF')
        print('CLOUD_RUN_OR_WORKER_CHANGED=NO')
        return 0
    except (Stop,base.Stop,ValueError,Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,(Stop,base.Stop)):
            code=str(exc)
        elif isinstance(exc,ValueError):
            code=str(exc) if str(exc) else 'course_readiness_failed'
        else:
            code=type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No secrets printed.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
