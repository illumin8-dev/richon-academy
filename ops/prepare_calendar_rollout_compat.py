"""Temporarily restore the reviewed DB018 calendar runtime grant profile.

Use only during the DB019 rolling transition so the currently tagged DB018
candidate and the new dual-profile candidate can both start. No schema/data
changes are performed.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import db
import portal_readiness as ready
import prepare_account_lifecycle as base

CONFIRM='RESTORE_DB018_CALENDAR_GRANTS'

class Stop(Exception):
    pass

def need(value,code):
    if not value: raise Stop(code)

def env_value(service,name):
    values=[item.get('value','') for item in
            service['spec']['template']['spec']['containers'][0].get('env',[])
            if item.get('name')==name]
    need(len(values)<=1,'duplicate_feature_flag')
    return values[0] if values else ''

def grant_legacy(cur):
    from psycopg import sql
    role=sql.Identifier(ready.ROLE)
    relation=sql.SQL('richon.calendar_events')
    cur.execute(sql.SQL('REVOKE ALL ON {} FROM {}').format(relation,role))
    cur.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(relation,role))
    cur.execute(sql.SQL('GRANT INSERT ({}) ON {} TO {}').format(
        sql.SQL(',').join(map(sql.Identifier,ready.CALENDAR_LEGACY_INSERT['calendar_events'])),relation,role))
    cur.execute(sql.SQL('GRANT UPDATE ({}) ON {} TO {}').format(
        sql.SQL(',').join(map(sql.Identifier,ready.CALENDAR_LEGACY_UPDATE['calendar_events'])),relation,role))
    cur.execute(sql.SQL('REVOKE DELETE,TRUNCATE,TRIGGER,REFERENCES ON {} FROM {}').format(relation,role))

def apply(owner_url,runtime_url):
    base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
    base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
    try:
        with db._connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='30s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,6)')
                cur.execute("SELECT to_regclass('richon.calendar_events') IS NOT NULL")
                need(cur.fetchone()==(True,),'calendar_table_missing')
                need(ready.calendar_schema_ready(cur),'db019_schema_missing')
                grant_legacy(cur)
                ready.check_role(cur)
        with db._connect(runtime_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                ready.check_cursor(cur)
                need(ready.calendar_grant_profile(cur)=='legacy','legacy_profile_not_active')
    except (Stop,ValueError):
        raise
    except Exception:
        raise Stop('calendar_compat_grant_failed') from None

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--diagnose',action='store_true')
    args=parser.parse_args()
    stage='cloud-target'
    try:
        project=base.gj('projects','describe',base.PROJECT)
        need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
        _,owner_version=base.secret_ref(base.OWNER_SERVICE,base.OWNER_SECRET)
        portal_service,runtime_version=base.secret_ref(base.PORTAL_SERVICE,base.RUNTIME_SECRET)
        need(env_value(portal_service,'RICHON_COURSE_DOMAIN_ENABLED')=='true','course_feature_not_enabled')
        print('TARGET=richon-academy / production Neon / DB019 rollout compatibility')
        print('SCOPE=restore exact DB018 calendar grants only / no schema or row changes')
        print('NO_DEPLOY=YES / NO_CUSTOMER_ROW_PRINTS=YES')
        stage='secret-access'
        owner_url=base.access(base.OWNER_SECRET,owner_version)
        runtime_url=base.access(base.RUNTIME_SECRET,runtime_version)
        base.validate_dsn(owner_url,base.OWNER_ROLE);base.validate_dsn(runtime_url,ready.ROLE)
        if args.diagnose:
            base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
            base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
            print('DIAGNOSE_ONLY=PASS / NO_DATABASE_CHANGES=YES');return 0
        if input('Type '+CONFIRM+' to continue: ').strip()!=CONFIRM:
            print('CANCELLED: no privilege changes made.');return 0
        os.environ['RICHON_TERMS_VERSION']='member-info-v1'
        os.environ['RICHON_PRIVACY_VERSION']='member-info-v1'
        os.environ['RICHON_ACCOUNT_ENABLED']='true'
        os.environ['RICHON_MARKETING_CONSENT_ENABLED']='true'
        os.environ['RICHON_COURSE_DOMAIN_ENABLED']='true'
        stage='database'
        apply(owner_url,runtime_url)
        print('CALENDAR_GRANT_PROFILE=LEGACY_COMPAT')
        print('RUNTIME_READBACK=PASS / SCHEMA_CHANGED=NO / CUSTOMER_ROWS_CHANGED=NO / NO_DEPLOY=YES')
        return 0
    except (Stop,ValueError):
        print('STOP='+stage+' / no secrets or customer rows printed');return 2
    except Exception:
        print('FAIL='+stage+' / no secrets or customer rows printed');return 1

if __name__=='__main__':
    raise SystemExit(main())
