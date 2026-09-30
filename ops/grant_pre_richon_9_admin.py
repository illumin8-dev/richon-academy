"""Owner-only grant of Pre리치온 9기 to the sole active admin member.

Writes at most one member-linked enrollment_learner, one course_enrollment,
and one course-domain audit row. It never changes members/profiles/orders/
payments/sessions/cloud configuration. Exact replay is a no-op.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import NAMESPACE_URL, uuid4, uuid5

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import diagnose_production_data as diag
import prepare_account_lifecycle as base
import create_pre_richon_9 as course

LEARNER_ID=uuid5(NAMESPACE_URL,'https://richonacademy.com/course-learners/pre-richon-9-admin')
ENROLLMENT_ID=uuid5(NAMESPACE_URL,'https://richonacademy.com/course-enrollments/pre-richon-9-admin')
REQUEST_ID=uuid5(NAMESPACE_URL,'https://richonacademy.com/course-ops/pre-richon-9-admin-grant-v1')
NOTE='Pre리치온 9기 관리자 수강권'
CONFIRM='GRANT_PRE_RICHON_9_TO_ADMIN'


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def validate_source():
    need(subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode==0
         and subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0,
         'tracked_checkout_not_clean')
    need((ROOT/'ops/create_pre_richon_9.py').is_file(),'course_seed_helper_missing')


def sole_admin(cur):
    cur.execute("""SELECT m.member_id,m.display_name,p.name,p.email,p.phone
        FROM richon.members m
        LEFT JOIN richon.member_profiles p ON p.member_id=m.member_id
        WHERE m.role='admin' AND m.status='active'
        ORDER BY m.member_id""")
    rows=cur.fetchall()
    need(len(rows)==1,'active_admin_count_not_one')
    row=rows[0]
    need(bool((row[2] or row[1] or '').strip()),'active_admin_name_missing')
    return row


def ensure_course_exact(cur):
    course.verify_schema(cur)
    cur.execute("""SELECT title,description,access_mode,fixed_months,archived_at
        FROM richon.course_programs WHERE program_id=%s""",(course.PROGRAM_ID,))
    program=cur.fetchone()
    need(program is not None and course.exact_program(program),'pre_richon_program_mismatch')

    cur.execute("""SELECT program_id,cohort_label,starts_on,ends_on,default_access_start,
        default_access_end,recruit_opens_at,recruit_closes_at,capacity,status,price_krw,archived_at
        FROM richon.course_runs WHERE run_id=%s""",(course.RUN_ID,))
    run=cur.fetchone()
    need(run is not None and course.exact_run(run),'pre_richon_9_run_mismatch')

    cur.execute("""SELECT count(*) FROM richon.course_runs
        WHERE program_id=%s AND cohort_label=%s""",(course.PROGRAM_ID,course.COHORT))
    need(cur.fetchone()==(1,),'pre_richon_9_duplicate_cohort')


def existing_state(cur,admin_id):
    cur.execute("""SELECT learner_id FROM richon.enrollment_learners
        WHERE member_id=%s""",(admin_id,))
    learner=cur.fetchone()

    if learner:
        learner_id=learner[0]
        cur.execute("""SELECT enrollment_id,access_start,access_end,source,note,
                             cancelled_at,suspended_at
            FROM richon.course_enrollments
            WHERE run_id=%s AND learner_id=%s""",(course.RUN_ID,learner_id))
        enrollment=cur.fetchone()
    else:
        learner_id=None
        enrollment=None

    # Deterministic IDs may not belong to another target.
    cur.execute('SELECT member_id FROM richon.enrollment_learners WHERE learner_id=%s',(LEARNER_ID,))
    deterministic_learner=cur.fetchone()
    if deterministic_learner is not None:
        need(deterministic_learner[0]==admin_id,'deterministic_learner_id_conflict')
        if learner_id is not None:
            need(learner_id==LEARNER_ID,'admin_has_different_learner_id')

    cur.execute('SELECT run_id,learner_id FROM richon.course_enrollments WHERE enrollment_id=%s',(ENROLLMENT_ID,))
    deterministic_enrollment=cur.fetchone()
    if deterministic_enrollment is not None:
        need(deterministic_enrollment==(course.RUN_ID,learner_id or LEARNER_ID),
             'deterministic_enrollment_id_conflict')

    if enrollment is not None:
        need(enrollment[0]==ENROLLMENT_ID,'existing_pre_richon_9_enrollment_conflict')
        need(enrollment[1]==course.START and enrollment[2]==course.END,
             'existing_pre_richon_9_access_conflict')
        need(enrollment[3]=='ADMIN' and enrollment[4]==NOTE,
             'existing_pre_richon_9_metadata_conflict')
        need(enrollment[5] is None and enrollment[6] is None,
             'existing_pre_richon_9_inactive')
    return learner_id,enrollment is not None


def fingerprint(operation,payload):
    return hashlib.sha256(
        json.dumps([operation,payload],sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
    ).hexdigest()


def create(owner_url):
    learner_created=False
    enrollment_created=False
    try:
        with diag.connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='20s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,10)')

                ensure_course_exact(cur)
                admin_id,display_name,profile_name,email,phone=sole_admin(cur)
                learner_id,enrollment_exists=existing_state(cur,admin_id)

                if learner_id is None:
                    learner_id=LEARNER_ID
                    cur.execute("""INSERT INTO richon.enrollment_learners
                        (learner_id,member_id,name,email,phone)
                        VALUES(%s,%s,%s,%s,%s)""",
                        (learner_id,admin_id,profile_name or display_name,email,phone))
                    learner_created=True

                if not enrollment_exists:
                    cur.execute("""INSERT INTO richon.course_enrollments
                        (enrollment_id,run_id,learner_id,status,access_start,access_end,source,note)
                        VALUES(%s,%s,%s,
                          CASE WHEN CURRENT_DATE<%s THEN 'SCHEDULED'
                               WHEN CURRENT_DATE>%s THEN 'COMPLETED'
                               ELSE 'ACTIVE' END,
                          %s,%s,'ADMIN',%s)""",
                        (ENROLLMENT_ID,course.RUN_ID,learner_id,
                         course.START,course.END,course.START,course.END,NOTE))

                    payload={
                        'run_id':str(course.RUN_ID),
                        'member_id':str(admin_id),
                        'access_start':None,
                        'access_end':None,
                        'note':NOTE,
                    }
                    result={
                        'enrollment_id':str(ENROLLMENT_ID),
                        'learner_id':str(learner_id),
                        'run_id':str(course.RUN_ID),
                        'source':'ADMIN',
                    }
                    cur.execute("""INSERT INTO richon.course_domain_audit
                        (event_id,actor_id,request_id,fingerprint,operation,entity_id,reason,result)
                        VALUES(%s,%s,%s,%s,'enrollment.grant',%s,%s,%s::jsonb)""",
                        (uuid4(),admin_id,REQUEST_ID,fingerprint('enrollment.grant',payload),
                         str(ENROLLMENT_ID),'Pre리치온 9기 관리자 수강권 지급',
                         json.dumps(result,ensure_ascii=True,separators=(',',':'))))
                    enrollment_created=True

                # Re-read inside the same transaction and fail closed.
                learner_id2,enrollment_exists2=existing_state(cur,admin_id)
                need(learner_id2==learner_id and enrollment_exists2,'grant_postcheck_failed')

    except Stop:
        raise
    except Exception:
        raise Stop('pre_richon_9_admin_grant_transaction_failed') from None
    return learner_created,enrollment_created


def readback(owner_url):
    try:
        with diag.connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                ensure_course_exact(cur)
                admin_id,*_=sole_admin(cur)
                learner_id,enrollment_exists=existing_state(cur,admin_id)
                need(learner_id is not None and enrollment_exists,'grant_readback_missing')
                cur.execute('SELECT count(*) FROM richon.course_sessions WHERE run_id=%s',(course.RUN_ID,))
                need(cur.fetchone()==(0,),'unexpected_session_rows')
    except Stop:
        raise
    except Exception:
        raise Stop('pre_richon_9_admin_grant_readback_failed') from None


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
        for flag in ('RICHON_ACCOUNT_ENABLED','RICHON_COURSE_DOMAIN_ENABLED'):
            need(diag.env_value(portal_service,flag)=='true','required_feature_not_enabled_'+flag.lower())

        print('TARGET=richon-academy / production Neon / Pre리치온 9기 admin enrollment')
        print('WRITE_SCOPE=ENROLLMENT_LEARNER_IF_NEEDED+COURSE_ENROLLMENT+COURSE_AUDIT')
        print('COURSE=Pre리치온 9기 / ACCESS=2026-10-08..2026-12-07 / SESSIONS=0')
        print('NO_MEMBER_PROFILE_CHANGES=YES / NO_ORDER_PAYMENT_CHANGES=YES / NO_CLOUD_CHANGES=YES')
        print('NO_CUSTOMER_ROWS_PRINTED=YES')

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
                ensure_course_exact(cur)
                admin_id,*_=sole_admin(cur)
                learner_id,enrollment_exists=existing_state(cur,admin_id)
        if enrollment_exists:
            print('ADMIN_ENROLLMENT=ALREADY_EXACT / DATABASE_CHANGED=NO')
            return 0

        if input('Type '+CONFIRM+' to continue: ').strip()!=CONFIRM:
            print('CANCELLED: no database changes made.')
            return 0

        stage='database'
        learner_created,enrollment_created=create(owner_url)
        stage='readback'
        readback(owner_url)

        print('LEARNER_LINK='+('CREATED' if learner_created else 'ALREADY_PRESENT'))
        print('ENROLLMENT='+('CREATED' if enrollment_created else 'ALREADY_EXACT'))
        print('SESSIONS=0')
        print('PRE_RICHON_9_ADMIN_ENROLLMENT=PASS')
        print('MEMBER_PROFILE_CHANGED=NO / ORDERS_CHANGED=NO / CLOUD_CHANGED=NO')
        return 0
    except (Stop,diag.Stop,base.Stop,ValueError,Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,(Stop,diag.Stop,base.Stop)):
            code=str(exc)
        elif isinstance(exc,ValueError):
            code=str(exc) or 'pre_richon_9_admin_grant_validation_failed'
        else:
            code=type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No secrets or customer rows printed.',file=sys.stderr)
        return 1
    finally:
        owner_url=runtime_url=None


if __name__=='__main__':
    raise SystemExit(main())
