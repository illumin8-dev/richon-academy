"""Owner-only DB021 preparation for enrollment adjustments.

Applies the reviewed adjustment ledger and refreshes the exact course-domain
runtime grants. Never deploys Cloud Run, changes feature flags, calls providers,
or prints credentials/customer rows.
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
import course_adjustment_migrate as adjustment
import portal_readiness as ready
import prepare_account_lifecycle as base
import prepare_course_domain as course

CONFIRM='APPLY_DB021_ENROLLMENT_ADJUSTMENTS'


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def checksum(version):
    return hashlib.sha256((adjustment.DIRECTORY/(version+'.sql')).read_bytes()).hexdigest()


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
    for version in (*adjustment.DEPENDENCIES,adjustment.VERSION):
        need((adjustment.DIRECTORY/(version+'.sql')).is_file(),'adjustment_migration_source_missing')
    need((ROOT/'backend/portal_readiness.py').is_file(),'readiness_missing')


def state(cur):
    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(adjustment.VERSION,))
    row=cur.fetchone()
    if row is None:return 'ABSENT'
    return 'EXACT' if row==(checksum(adjustment.VERSION),) else 'MISMATCH'


def apply_migration(cur):
    current=state(cur)
    if current=='EXACT':return False
    need(current=='ABSENT','db021_checksum_mismatch')
    for version in adjustment.DEPENDENCIES:
        cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
        need(cur.fetchone()==(adjustment.checksum(version),),'dependency_mismatch_'+version)
    cur.execute((adjustment.DIRECTORY/(adjustment.VERSION+'.sql')).read_text())
    cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                (adjustment.VERSION,checksum(adjustment.VERSION)))
    need(state(cur)=='EXACT','db021_readback_failed')
    return True


def prepare(owner_url,runtime_url):
    base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
    base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
    changed=False
    try:
        with db._connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='45s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,7)')
                changed=apply_migration(cur)
                course.grant_course(cur)
                ready.check_role(cur)
    except (Stop,course.Stop,ValueError):
        raise
    except Exception:
        raise Stop('db021_grant_transaction_failed') from None

    try:
        with db._connect(runtime_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='10s'")
                ready.check_cursor(cur)
                cur.execute('SELECT 1 FROM richon.course_enrollment_adjustments LIMIT 0')
    except Exception:
        raise Stop('db021_runtime_readback_failed') from None

    try:
        with db._connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                need(state(cur)=='EXACT','db021_final_checksum_failed')
                cur.execute("SELECT to_regclass('richon.course_enrollment_adjustments') IS NOT NULL")
                need(cur.fetchone()==(True,),'db021_table_missing')
    except Stop:
        raise
    except Exception:
        raise Stop('db021_owner_readback_failed') from None
    return changed


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
        need(env_value(portal_service,'RICHON_COURSE_DOMAIN_ENABLED')=='true','course_feature_not_enabled')
        monthly_flag=env_value(portal_service,'RICHON_MONTHLY_ENABLED') or 'false'
        manual_flag=env_value(portal_service,'RICHON_MANUAL_ENABLED') or 'false'
        need(monthly_flag in ('true','false') and manual_flag in ('true','false'),'invalid_legacy_feature_flag')

        print('TARGET=richon-academy / production Neon / protected portal candidate')
        print('SCOPE=DB021 adjustment ledger + exact course runtime grants')
        print('NO_DEPLOY=YES / NO_CUSTOMER_ROW_CHANGES=YES')

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
                current=state(cur)
                need(current!='MISMATCH','db021_checksum_mismatch')
        print('DB021='+current)

        if args.diagnose:
            print('DIAGNOSE_ONLY=PASS / NO_DATABASE_CHANGES=YES')
            return 0

        if input('Type '+CONFIRM+' to continue: ').strip()!=CONFIRM:
            print('CANCELLED: no database changes made.')
            return 0

        # Match the already-running portal contract while checking grants.
        os.environ['RICHON_TERMS_VERSION']='member-info-v1'
        os.environ['RICHON_PRIVACY_VERSION']='member-info-v1'
        os.environ['RICHON_ACCOUNT_ENABLED']='true'
        os.environ['RICHON_MARKETING_CONSENT_ENABLED']='true'
        os.environ['RICHON_COURSE_DOMAIN_ENABLED']='true'
        os.environ['RICHON_MONTHLY_ENABLED']=monthly_flag
        os.environ['RICHON_MANUAL_ENABLED']=manual_flag

        stage='database'
        changed=prepare(owner_url,runtime_url)
        print('DB021='+('APPLIED' if changed else 'ALREADY_APPLIED'))
        print('COURSE_RUNTIME_GRANTS=PASS / RUNTIME_READBACK=PASS')
        print('CUSTOMER_ROWS_CHANGED=NO / CLOUD_RUN_OR_WORKER_CHANGED=NO')
        return 0
    except (Stop,course.Stop,base.Stop,ValueError,Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,(Stop,course.Stop,base.Stop)):
            code=str(exc)
        elif isinstance(exc,ValueError):
            code=str(exc) or 'db021_readiness_failed'
        else:
            code=type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No secrets printed.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
