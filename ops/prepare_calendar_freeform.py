"""Owner-run DB019 free-form calendar preparation + exact runtime grants.

Requires DB018 already applied. The first DB019 apply refuses to proceed if
calendar_events already contains rows, so changing the admin calendar model
cannot silently reinterpret an operator-created schedule.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import db
import calendar_freeform_migrate as migration
import portal_readiness as ready
import prepare_account_lifecycle as base

CONFIRM='APPLY_DB019_CALENDAR_FREEFORM'

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

def grant_calendar(cur):
    from psycopg import sql
    role=sql.Identifier(ready.ROLE)
    relation=sql.SQL('richon.calendar_events')
    cur.execute(sql.SQL('REVOKE ALL ON {} FROM {}').format(relation,role))
    cur.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(relation,role))
    cur.execute(sql.SQL('GRANT INSERT ({}) ON {} TO {}').format(
        sql.SQL(',').join(map(sql.Identifier,ready.CALENDAR_INSERT['calendar_events'])),relation,role))
    cur.execute(sql.SQL('GRANT UPDATE ({}) ON {} TO {}').format(
        sql.SQL(',').join(map(sql.Identifier,ready.CALENDAR_UPDATE['calendar_events'])),relation,role))
    cur.execute(sql.SQL('REVOKE DELETE,TRUNCATE,TRIGGER,REFERENCES ON {} FROM {}').format(relation,role))

def apply(owner_url,runtime_url):
    base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
    base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
    changed=False
    try:
        with db._connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='30s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,5)')
                for dep in migration.DEPENDENCIES:
                    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(dep,))
                    need(cur.fetchone()==(migration.checksum(dep),),'dependency_mismatch_'+dep)
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(migration.VERSION,))
                row=cur.fetchone();expected=migration.checksum(migration.VERSION)
                if row is None:
                    cur.execute('SELECT NOT EXISTS(SELECT 1 FROM richon.calendar_events LIMIT 1)')
                    need(cur.fetchone()==(True,),'calendar_events_not_empty')
                    cur.execute((migration.DIRECTORY/(migration.VERSION+'.sql')).read_text())
                    cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                                (migration.VERSION,expected))
                    changed=True
                else:
                    need(row==(expected,),'calendar_freeform_checksum_mismatch')
                grant_calendar(cur)
                ready.check_role(cur)
    except (Stop,ValueError):
        raise
    except Exception:
        raise Stop('calendar_freeform_database_transaction_failed') from None
    try:
        with db._connect(runtime_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute('SELECT event_id,course_label,content_text,color_hex FROM richon.calendar_events LIMIT 0')
                ready.check_cursor(cur)
    except (Stop,ValueError):
        raise
    except Exception:
        raise Stop('calendar_freeform_runtime_readback_failed') from None
    return changed

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--diagnose',action='store_true')
    args=parser.parse_args()
    stage='source'
    try:
        need((ROOT/'backend/migrations/019_calendar_freeform.sql').is_file(),'db019_missing')
        need((ROOT/'backend/portal_readiness.py').is_file(),'readiness_missing')
        stage='cloud-target'
        project=base.gj('projects','describe',base.PROJECT)
        need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
        _,owner_version=base.secret_ref(base.OWNER_SERVICE,base.OWNER_SECRET)
        portal_service,runtime_version=base.secret_ref(base.PORTAL_SERVICE,base.RUNTIME_SECRET)
        need(env_value(portal_service,'RICHON_COURSE_DOMAIN_ENABLED')=='true','course_feature_not_enabled')
        print('TARGET=richon-academy / production Neon / free-form admin calendar')
        print('SCOPE=DB019 free-form fields + exact richon_portal_login grants')
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
            print('CANCELLED: no database changes made.');return 0
        os.environ['RICHON_TERMS_VERSION']='member-info-v1'
        os.environ['RICHON_PRIVACY_VERSION']='member-info-v1'
        os.environ['RICHON_ACCOUNT_ENABLED']='true'
        os.environ['RICHON_MARKETING_CONSENT_ENABLED']='true'
        os.environ['RICHON_COURSE_DOMAIN_ENABLED']='true'
        stage='database'
        changed=apply(owner_url,runtime_url)
        print('DB019='+('APPLIED' if changed else 'ALREADY_APPLIED'))
        print('CALENDAR_FREEFORM_RUNTIME_GRANTS=PASS')
        print('RUNTIME_READBACK=PASS / NO_DEPLOY=YES')
        return 0
    except (Stop,ValueError):
        print('STOP='+stage+' / no secrets or customer rows printed');return 2
    except Exception:
        print('FAIL='+stage+' / no secrets or customer rows printed');return 1

if __name__=='__main__':
    raise SystemExit(main())
