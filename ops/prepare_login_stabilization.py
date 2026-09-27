"""Owner-run production preparation for login stabilization (DB012 + exact runtime grants).

Applies only the reviewed temporary social-profile columns, grants INSERT on those
columns to richon_portal_login, and removes self-service UPDATE(name). It does not
deploy Cloud Run/Cloudflare, call Kakao/Naver, or print secrets/customer rows.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

import db
import oauth_signup_profile_migrate as migration
import portal_readiness as ready
import prepare_account_lifecycle as base

MINIMUM_SOURCE='36611384f597e47bcda7718209c43d3b411e5984'
CONFIRM='APPLY_DB012'


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def validate_source():
    need(base.command(['git','merge-base','--is-ancestor',MINIMUM_SOURCE,'HEAD'])=='',
         'required_source_not_present')
    need(subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode==0
         and subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0,
         'tracked_checkout_not_clean')
    need((migration.DIRECTORY/(migration.VERSION+'.sql')).is_file(),'db012_missing')
    need((ROOT/'backend/portal_readiness.py').is_file(),'readiness_missing')


def env_value(service,name):
    values=[item.get('value','') for item in
            service['spec']['template']['spec']['containers'][0].get('env',[])
            if item.get('name')==name]
    need(len(values)<=1,'duplicate_feature_flag')
    return values[0] if values else ''


def apply(owner_url,runtime_url):
    base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
    base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
    path=migration.DIRECTORY/(migration.VERSION+'.sql')
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    changed=False

    try:
        with db._connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='30s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,1)')
                for version in migration.DEPENDENCIES:
                    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
                    need(cur.fetchone()==(migration.checksum(version),),
                         'dependency_mismatch_'+version)
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',
                            (migration.VERSION,))
                old=cur.fetchone()
                if old is None:
                    cur.execute(path.read_text())
                    cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                                (migration.VERSION,checksum))
                    changed=True
                else:
                    need(old==(checksum,),'db012_checksum_mismatch')

                cur.execute('''GRANT INSERT (provider_name,provider_phone,provider_email)
                               ON richon.oauth_signups TO richon_portal_login''')
                cur.execute('''REVOKE UPDATE (name)
                               ON richon.member_profiles FROM richon_portal_login''')
                ready.check_role(cur)
    except Stop:
        raise
    except Exception:
        raise Stop('db012_transaction_failed') from None

    try:
        with db._connect(runtime_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='10s'")
                ready.check_cursor(cur)
    except Stop:
        raise
    except Exception:
        raise Stop('runtime_readback_failed') from None

    try:
        with db._connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',
                            (migration.VERSION,))
                need(cur.fetchone()==(checksum,),'db012_readback_failed')
                cur.execute("""SELECT
                    EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_schema='richon' AND table_name='oauth_signups'
                              AND column_name='provider_name'),
                    EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_schema='richon' AND table_name='oauth_signups'
                              AND column_name='provider_phone'),
                    EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_schema='richon' AND table_name='oauth_signups'
                              AND column_name='provider_email')""")
                need(cur.fetchone()==(True,True,True),'db012_columns_missing')
    except Stop:
        raise
    except Exception:
        raise Stop('owner_final_readback_failed') from None
    return changed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--diagnose',action='store_true',
                        help='Read-only source/cloud/database checks. Does not apply DB012 or grants.')
    args=parser.parse_args()
    stage='source'
    try:
        validate_source()
        stage='cloud-target'
        project=base.gj('projects','describe',base.PROJECT)
        need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
        _,owner_version=base.secret_ref(base.OWNER_SERVICE,base.OWNER_SECRET)
        portal_service,runtime_version=base.secret_ref(base.PORTAL_SERVICE,base.RUNTIME_SECRET)
        need(env_value(portal_service,'RICHON_ACCOUNT_ENABLED')=='true','account_feature_not_enabled')
        need(env_value(portal_service,'RICHON_MARKETING_CONSENT_ENABLED')=='true','marketing_feature_not_enabled')

        print('TARGET=richon-academy / production Neon / protected portal candidate')
        print('SCOPE=DB012 + oauth_signups provider-field INSERT grants + member name UPDATE revoke')
        print('NO_DEPLOY=YES / NO_PROVIDER_CALLS=YES / NO_CUSTOMER_ROW_PRINTS=YES')

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

        os.environ['RICHON_TERMS_VERSION']='member-info-v1'
        os.environ['RICHON_PRIVACY_VERSION']='member-info-v1'
        os.environ['RICHON_ACCOUNT_ENABLED']='true'
        os.environ['RICHON_MARKETING_CONSENT_ENABLED']='true'

        stage='database'
        changed=apply(owner_url,runtime_url)
        print('DB012='+('APPLIED' if changed else 'ALREADY_APPLIED'))
        print('RUNTIME_MINIMUM_PRIVILEGES=PASS')
        print('RUNTIME_READBACK=PASS')
        print('CLOUD_RUN_OR_WORKER_CHANGED=NO')
        return 0
    except (Stop,base.Stop,Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,(Stop,base.Stop)):
            code=str(exc)
        else:
            code=type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No secrets printed.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
