"""Owner-only creation of the approved Pre리치온 9기 program/run.

Creates only the canonical program and run plus course-domain audit records.
No sessions, enrollments, learners, members, orders, payments, Cloud Run, IAM,
feature flags or provider state are changed. Re-running exact state is read-only.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import NAMESPACE_URL, uuid4, uuid5

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import diagnose_production_data as diag
import prepare_account_lifecycle as base
import prepare_course_domain as prep

PROGRAM_ID='pre-richon'
PROGRAM_TITLE='Pre리치온 (프리리치온)'
PROGRAM_DESCRIPTION='투자원칙, 갭투자, 서울 초기재개발, 시장구조부터 분양권, 지방 재개발, 경매까지 다루는 입문 과정.'
COHORT='Pre리치온 9기'
START=date(2026,10,8)
END=date(2026,12,7)
PRICE_KRW=176000
STATUS='OPEN'
RUN_ID=uuid5(NAMESPACE_URL,'https://richonacademy.com/course-runs/pre-richon-9')
PROGRAM_REQUEST=uuid5(NAMESPACE_URL,'https://richonacademy.com/course-ops/pre-richon-program-v1')
RUN_REQUEST=uuid5(NAMESPACE_URL,'https://richonacademy.com/course-ops/pre-richon-9-run-v1')
CONFIRM='CREATE_PRE_RICHON_9'


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def validate_source():
    need(subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode==0
         and subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0,
         'tracked_checkout_not_clean')
    need((ROOT/'backend/migrations/015_course_run_foundation.sql').is_file(),'db015_source_missing')
    need((ROOT/'backend/migrations/016_course_entitlements.sql').is_file(),'db016_source_missing')


def verify_schema(cur):
    for migration in (prep.domain,prep.entitlements):
        cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(migration.VERSION,))
        need(cur.fetchone()==(prep.migration_checksum(migration),),
             migration.VERSION+'_checksum_mismatch')
    cur.execute("""SELECT
        to_regclass('richon.course_programs') IS NOT NULL,
        to_regclass('richon.course_runs') IS NOT NULL,
        to_regclass('richon.course_sessions') IS NOT NULL,
        to_regclass('richon.course_enrollments') IS NOT NULL,
        to_regclass('richon.course_domain_audit') IS NOT NULL""")
    need(cur.fetchone()==(True,True,True,True,True),'course_schema_missing')


def exact_program(row):
    return row==(PROGRAM_TITLE,PROGRAM_DESCRIPTION,'fixed_months',2,None)


def exact_run(row):
    return row==(PROGRAM_ID,COHORT,START,END,START,END,None,None,None,STATUS,PRICE_KRW,None)


def target_state(cur):
    cur.execute("""SELECT title,description,access_mode,fixed_months,archived_at
        FROM richon.course_programs WHERE program_id=%s""",(PROGRAM_ID,))
    program=cur.fetchone()
    if program is not None:
        need(exact_program(program),'pre_richon_program_conflict')

    cur.execute("""SELECT program_id,cohort_label,starts_on,ends_on,default_access_start,
        default_access_end,recruit_opens_at,recruit_closes_at,capacity,status,price_krw,archived_at
        FROM richon.course_runs WHERE run_id=%s""",(RUN_ID,))
    by_id=cur.fetchone()

    cur.execute("""SELECT run_id FROM richon.course_runs
        WHERE program_id=%s AND cohort_label=%s""",(PROGRAM_ID,COHORT))
    cohort_rows=cur.fetchall()
    need(len(cohort_rows)<=1,'pre_richon_9_duplicate_cohort')
    if cohort_rows:
        need(cohort_rows[0][0]==RUN_ID,'pre_richon_9_run_id_conflict')
    if by_id is not None:
        need(exact_run(by_id),'pre_richon_9_run_conflict')
        need(bool(cohort_rows),'pre_richon_9_cohort_missing')

    cur.execute('SELECT count(*) FROM richon.course_sessions WHERE run_id=%s',(RUN_ID,))
    sessions=cur.fetchone()[0]
    cur.execute('SELECT count(*) FROM richon.course_enrollments WHERE run_id=%s',(RUN_ID,))
    enrollments=cur.fetchone()[0]
    need(sessions==0,'pre_richon_9_sessions_already_exist')
    need(enrollments==0,'pre_richon_9_enrollments_already_exist')
    return program is not None,by_id is not None


def actor(cur):
    cur.execute("""SELECT member_id FROM richon.members
        WHERE role='admin' AND status='active' ORDER BY member_id""")
    rows=cur.fetchall()
    need(len(rows)==1,'active_admin_count_not_one')
    return rows[0][0]


def fingerprint(operation,payload):
    return hashlib.sha256(
        json.dumps([operation,payload],sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
    ).hexdigest()


def audit(cur,admin,request_id,operation,entity,reason,result,payload):
    cur.execute("""INSERT INTO richon.course_domain_audit
        (event_id,actor_id,request_id,fingerprint,operation,entity_id,reason,result)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
        (uuid4(),admin,request_id,fingerprint(operation,payload),operation,
         str(entity),reason,json.dumps(result,ensure_ascii=True,separators=(',',':'))))


def create(owner_url):
    program_created=False
    run_created=False
    try:
        with diag.connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='20s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,9)')
                verify_schema(cur)
                program_exists,run_exists=target_state(cur)
                admin=actor(cur)

                if not program_exists:
                    cur.execute("""INSERT INTO richon.course_programs
                        (program_id,title,description,access_mode,fixed_months)
                        VALUES(%s,%s,%s,'fixed_months',2)""",
                        (PROGRAM_ID,PROGRAM_TITLE,PROGRAM_DESCRIPTION))
                    payload={'program_id':PROGRAM_ID,'title':PROGRAM_TITLE,
                             'description':PROGRAM_DESCRIPTION,'access_mode':'fixed_months','fixed_months':2}
                    audit(cur,admin,PROGRAM_REQUEST,'program.create',PROGRAM_ID,
                          'Pre리치온 운영 프로그램 생성',
                          {'program_id':PROGRAM_ID,'version':1},payload)
                    program_created=True

                if not run_exists:
                    cur.execute("""INSERT INTO richon.course_runs
                        (run_id,program_id,cohort_label,starts_on,ends_on,
                         default_access_start,default_access_end,recruit_opens_at,recruit_closes_at,
                         capacity,status,price_krw)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,NULL,NULL,NULL,%s,%s)""",
                        (RUN_ID,PROGRAM_ID,COHORT,START,END,START,END,STATUS,PRICE_KRW))
                    payload={'run_id':str(RUN_ID),'program_id':PROGRAM_ID,'cohort_label':COHORT,
                             'starts_on':START.isoformat(),'ends_on':END.isoformat(),
                             'default_access_start':START.isoformat(),'default_access_end':END.isoformat(),
                             'recruit_opens_at':None,'recruit_closes_at':None,'capacity':None,
                             'status':STATUS,'price_krw':PRICE_KRW}
                    audit(cur,admin,RUN_REQUEST,'run.create',RUN_ID,
                          'Pre리치온 9기 기본정보 생성',
                          {'run_id':str(RUN_ID),'program_id':PROGRAM_ID,'version':1},payload)
                    run_created=True

                # Fail closed if anything outside the approved empty schedule/enrollment scope appeared.
                target_state(cur)
    except Stop:
        raise
    except Exception:
        raise Stop('pre_richon_9_transaction_failed') from None
    return program_created,run_created


def readback(owner_url):
    try:
        with diag.connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='10s'")
                verify_schema(cur)
                program_exists,run_exists=target_state(cur)
                need(program_exists and run_exists,'pre_richon_9_readback_missing')
    except Stop:
        raise
    except Exception:
        raise Stop('pre_richon_9_readback_failed') from None


def main():
    stage='source'
    owner_url=runtime_url=None
    try:
        validate_source()
        stage='cloud-target'
        project=diag.gcloud_json('project_describe_failed','projects','describe',base.PROJECT)
        need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
        _,owner_version=diag.secret_ref(base.OWNER_SERVICE,base.OWNER_SECRET,'owner_service_describe_failed')
        portal_service,runtime_version=diag.secret_ref(
            base.PORTAL_SERVICE,base.RUNTIME_SECRET,'portal_service_describe_failed')
        for flag in ('RICHON_ACCOUNT_ENABLED','RICHON_MARKETING_CONSENT_ENABLED','RICHON_COURSE_DOMAIN_ENABLED'):
            need(diag.env_value(portal_service,flag)=='true','required_feature_not_enabled_'+flag.lower())

        print('TARGET=richon-academy / production Neon / Pre리치온 9기')
        print('WRITE_SCOPE=PROGRAM+RUN+COURSE_AUDIT_ONLY / SESSIONS=0 / ENROLLMENTS=0')
        print('PROGRAM=Pre리치온 / COHORT=9기 / ACCESS=2026-10-08..2026-12-07 / PRICE_KRW=176000')
        print('NO_MEMBER_ROW_CHANGES=YES / NO_ORDER_PAYMENT_CHANGES=YES / NO_CLOUD_CHANGES=YES')

        stage='secret-access'
        owner_url=diag.secret_access(base.OWNER_SECRET,owner_version,'owner_secret_access_failed')
        runtime_url=diag.secret_access(base.RUNTIME_SECRET,runtime_version,'runtime_secret_access_failed')
        owner_target=base.validate_dsn(owner_url,base.OWNER_ROLE)
        runtime_target=base.validate_dsn(runtime_url,'richon_portal_login')
        need(owner_target.hostname.replace('-pooler.','.')==
             runtime_target.hostname.replace('-pooler.','.'),'database_endpoint_mismatch')
        diag.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
        diag.diagnose_connection(runtime_url,'richon_portal_login','runtime')
        print('TLS_MODE=verify-full / TLS_CA=system-file')

        stage='preflight'
        with diag.connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                verify_schema(cur)
                program_exists,run_exists=target_state(cur)
                actor(cur)
        if program_exists and run_exists:
            print('PRE_RICHON_9=ALREADY_EXACT / DATABASE_CHANGED=NO')
            return 0

        if input('Type '+CONFIRM+' to continue: ').strip()!=CONFIRM:
            print('CANCELLED: no database changes made.')
            return 0

        stage='database'
        program_created,run_created=create(owner_url)
        stage='readback'
        readback(owner_url)

        print('PROGRAM='+('CREATED' if program_created else 'ALREADY_EXACT'))
        print('RUN='+('CREATED' if run_created else 'ALREADY_EXACT'))
        print('SESSIONS=0 / ENROLLMENTS=0')
        print('PRE_RICHON_9=PASS')
        print('MEMBER_ROWS_CHANGED=NO / ORDERS_CHANGED=NO / CLOUD_CHANGED=NO')
        return 0
    except (Stop,diag.Stop,base.Stop,ValueError,Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,(Stop,diag.Stop,base.Stop)):
            code=str(exc)
        elif isinstance(exc,ValueError):
            code=str(exc) or 'pre_richon_9_validation_failed'
        else:
            code=type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No secrets or customer rows printed.',file=sys.stderr)
        return 1
    finally:
        owner_url=runtime_url=None


if __name__=='__main__':
    raise SystemExit(main())
