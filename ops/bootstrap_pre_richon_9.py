"""One-time guarded bootstrap for Pre리치온 9기.

Default execution is read-only diagnosis. --apply still requires the exact interactive
confirmation phrase. Writes use the existing restricted portal runtime role and
course_domain_store.mutate(), so the same validation/audit path as the admin API is used.

No member/customer identifiers, contact data, DSNs, secret payloads or generated UUIDs
are printed.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import os
from pathlib import Path
import subprocess
import sys
from uuid import NAMESPACE_URL, UUID, uuid5

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import course_domain_models as model
import course_domain_store as store
import diagnose_production_data as diag
import prepare_account_lifecycle as base
import portal_readiness as ready

CONFIRM='APPLY_PRE_RICHON_9'
PROGRAM_ID='pre-richon'
PROGRAM_TITLE='Pre리치온 (프리리치온)'
COHORT='Pre리치온 9기'
PRICE_KRW=132000
START_ON=date(2026,10,1)
RUN_END=date(2026,11,30)
ACCESS_START=date(2026,10,1)
ACCESS_END=date(2026,11,30)
PROGRAM_DESCRIPTION='7주 온라인 강의 + 8주차 현장 임장으로 구성된 2개월 입문 과정. 8주차 현장 임장 일정은 추후 공지.'

SESSIONS=(
    (1,'2026-10-01T21:00:00+09:00','2026-10-01T23:00:00+09:00','부동산 투자원칙','리치온초이'),
    (2,'2026-10-08T21:00:00+09:00','2026-10-08T23:00:00+09:00','갭투자','가위남'),
    (3,'2026-10-15T21:00:00+09:00','2026-10-15T23:00:00+09:00','서울초기재개발','후니동산'),
    (4,'2026-10-22T21:00:00+09:00','2026-10-22T23:00:00+09:00','부동산 기초 및 시장구조','이루민'),
    (5,'2026-10-29T21:00:00+09:00','2026-10-29T23:00:00+09:00','분양권 전략','키네스트'),
    (6,'2026-11-05T21:00:00+09:00','2026-11-05T23:00:00+09:00','지방 재개발','재부스'),
    (7,'2026-11-12T21:00:00+09:00','2026-11-12T23:00:00+09:00','경매 권리분석 및 수익화','인생곰부'),
)


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def request_id(name):
    return uuid5(NAMESPACE_URL,'https://richonacademy.com/bootstrap/pre-richon-9/'+name)


def program_body():
    return model.ProgramCreate(
        request_id=request_id('program'),
        reason='Pre리치온 9기 운영 등록',
        program_id=PROGRAM_ID,
        title=PROGRAM_TITLE,
        description=PROGRAM_DESCRIPTION,
        access_mode='fixed_months',
        fixed_months=2,
    )


def run_body():
    return model.RunCreate(
        request_id=request_id('run'),
        reason='Pre리치온 9기 운영 등록',
        program_id=PROGRAM_ID,
        cohort_label=COHORT,
        starts_on=START_ON,
        ends_on=RUN_END,
        default_access_start=ACCESS_START,
        default_access_end=ACCESS_END,
        recruit_opens_at=None,
        recruit_closes_at=None,
        capacity=None,
        status='OPEN',
        price_krw=PRICE_KRW,
    )


def session_body(run_id, spec):
    sequence_no,starts_at,ends_at,title,mentor=spec
    return model.SessionCreate(
        request_id=request_id('session-'+str(sequence_no)),
        reason='Pre리치온 9기 1~7주 온라인 회차 등록',
        run_id=run_id,
        sequence_no=sequence_no,
        title=title,
        mentor_name=mentor,
        starts_at=datetime.fromisoformat(starts_at),
        ends_at=datetime.fromisoformat(ends_at),
        video_url=None,
        material_url=None,
    )


def enrollment_body(run_id,member_id):
    return model.EnrollmentGrant(
        request_id=request_id('enrollment-sole-active-admin'),
        reason='Pre리치온 9기 내 강의 운영 검증',
        run_id=run_id,
        member_id=member_id,
        learner_id=None,
        profile=None,
        access_start=None,
        access_end=None,
        note='Pre리치온 9기 운영 검증용 관리자 수강권',
    )


def validate_source():
    need(subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode==0
         and subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0,
         'tracked_checkout_not_clean')
    for path in (
        ROOT/'backend/course_domain_store.py',
        ROOT/'backend/course_domain_models.py',
        ROOT/'backend/migrations/015_course_run_foundation.sql',
        ROOT/'backend/migrations/016_course_entitlements.sql',
    ):
        need(path.is_file(),'course_source_missing')


def runtime_target():
    project=diag.gcloud_json('project_describe_failed','projects','describe',base.PROJECT)
    need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
    portal_service,runtime_version=diag.secret_ref(
        base.PORTAL_SERVICE,base.RUNTIME_SECRET,'portal_service_describe_failed')
    need(diag.env_value(portal_service,'RICHON_ACCOUNT_ENABLED')=='true',
         'account_feature_not_enabled')
    need(diag.env_value(portal_service,'RICHON_COURSE_DOMAIN_ENABLED')=='true',
         'course_feature_not_enabled')
    runtime_url=diag.secret_access(
        base.RUNTIME_SECRET,runtime_version,'runtime_secret_access_failed')
    base.validate_dsn(runtime_url,ready.ROLE)
    diag.diagnose_connection(runtime_url,ready.ROLE,'runtime')
    return runtime_url


def preflight(runtime_url):
    with diag.connect(runtime_url) as conn:
        conn.read_only=True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='10s'")
            cur.execute("""SELECT member_id FROM richon.members
                WHERE role='admin' AND status='active'
                ORDER BY created_at,member_id""")
            admins=cur.fetchall()
            need(len(admins)==1,'sole_active_admin_required')
            actor=admins[0][0]

            cur.execute("SELECT count(*) FROM richon.course_programs WHERE program_id<>%s",(PROGRAM_ID,))
            need(cur.fetchone()==(0,),'foreign_course_program_exists')
            cur.execute("""SELECT count(*) FROM richon.course_runs r
                WHERE r.program_id<>%s OR coalesce(r.cohort_label,'')<>%s""",(PROGRAM_ID,COHORT))
            need(cur.fetchone()==(0,),'foreign_course_run_exists')
            cur.execute("""SELECT count(*) FROM richon.course_sessions s
                JOIN richon.course_runs r USING(run_id)
                WHERE r.program_id<>%s OR coalesce(r.cohort_label,'')<>%s""",(PROGRAM_ID,COHORT))
            need(cur.fetchone()==(0,),'foreign_course_session_exists')
            cur.execute("""SELECT count(*) FROM richon.course_enrollments e
                JOIN richon.course_runs r USING(run_id)
                WHERE r.program_id<>%s OR coalesce(r.cohort_label,'')<>%s""",(PROGRAM_ID,COHORT))
            need(cur.fetchone()==(0,),'foreign_course_enrollment_exists')
            return actor


def apply(runtime_url,actor):
    os.environ['DATABASE_URL']=runtime_url

    program=store.mutate(actor,'program.create',program_body())
    need(program.get('program_id')==PROGRAM_ID,'program_create_failed')

    run=store.mutate(actor,'run.create',run_body())
    try:
        run_id=UUID(str(run['run_id']))
    except (KeyError,ValueError,TypeError):
        raise Stop('run_create_failed') from None

    for spec in SESSIONS:
        result=store.mutate(actor,'session.create',session_body(run_id,spec))
        need(result.get('run_id')==str(run_id),'session_create_failed')

    enrollment=store.mutate(actor,'enrollment.grant',enrollment_body(run_id,actor))
    need(enrollment.get('run_id')==str(run_id),'enrollment_create_failed')
    return run_id


def verify(runtime_url,actor,run_id):
    with diag.connect(runtime_url) as conn:
        conn.read_only=True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='10s'")
            cur.execute("""SELECT title,description,access_mode,fixed_months,archived_at IS NULL
                FROM richon.course_programs WHERE program_id=%s""",(PROGRAM_ID,))
            need(cur.fetchone()==(PROGRAM_TITLE,PROGRAM_DESCRIPTION,'fixed_months',2,True),
                 'program_readback_failed')

            cur.execute("""SELECT program_id,cohort_label,starts_on,ends_on,
                    default_access_start,default_access_end,status,price_krw,archived_at IS NULL
                FROM richon.course_runs WHERE run_id=%s""",(run_id,))
            need(cur.fetchone()==(PROGRAM_ID,COHORT,START_ON,RUN_END,ACCESS_START,ACCESS_END,
                                  'OPEN',PRICE_KRW,True),'run_readback_failed')

            cur.execute("""SELECT sequence_no,title,mentor_name,
                    to_char(starts_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI'),
                    to_char(ends_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD HH24:MI')
                FROM richon.course_sessions WHERE run_id=%s
                ORDER BY sequence_no""",(run_id,))
            actual=cur.fetchall()
            expected=[(seq,title,mentor,
                       datetime.fromisoformat(start).strftime('%Y-%m-%d %H:%M'),
                       datetime.fromisoformat(end).strftime('%Y-%m-%d %H:%M'))
                      for seq,start,end,title,mentor in SESSIONS]
            need(actual==expected,'session_readback_failed')

            cur.execute("""SELECT count(*) FROM richon.course_enrollments e
                JOIN richon.enrollment_learners l USING(learner_id)
                WHERE e.run_id=%s AND l.member_id=%s AND e.status<>'CANCELLED'""",
                (run_id,actor))
            need(cur.fetchone()==(1,),'enrollment_readback_failed')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    stage='source'
    runtime_url=None
    try:
        validate_source()
        stage='cloud-target'
        runtime_url=runtime_target()
        stage='preflight'
        actor=preflight(runtime_url)

        print('TARGET=richon-academy / production course domain / Pre리치온 9기')
        print('PLAN=PROGRAM:1 / RUN:1 / ONLINE_SESSIONS:7 / WEEK8_FIELD_TRIP:DEFERRED / ENROLLMENT:1')
        print('COURSE=Pre리치온 (프리리치온) / COHORT=Pre리치온 9기 / PRICE_KRW=132000')
        print('RUN_WINDOW=2026-10-01..2026-11-30 / ACCESS_WINDOW=2026-10-01..2026-11-30')
        print('ONLINE=THU 21:00-23:00 / 2026-10-01..2026-11-12 / WEEK8_DATE=TBD')
        print('TARGET_MEMBER=SOLE_ACTIVE_ADMIN / IDENTIFIER_NOT_PRINTED=YES')
        print('WRITE_PATH=course_domain_store.mutate / RUNTIME_ROLE=richon_portal_login')
        print('NO_SECRET_OUTPUT=YES / NO_CONTACT_OUTPUT=YES')

        if not args.apply:
            print('DIAGNOSE_ONLY=PASS / DATABASE_CHANGED=NO')
            return 0

        if input('Type '+CONFIRM+' to continue: ').strip()!=CONFIRM:
            print('CANCELLED: no production course rows changed.')
            return 0

        stage='course-write'
        run_id=apply(runtime_url,actor)
        stage='readback'
        verify(runtime_url,actor,run_id)

        print('PRE_RICHON_9_BOOTSTRAP=PASS')
        print('PROGRAM=PASS / RUN=PASS / ONLINE_SESSIONS=7 / WEEK8=DEFERRED')
        print('ENROLLMENT=PASS / TARGET=SOLE_ACTIVE_ADMIN / IDENTIFIER_NOT_PRINTED=YES')
        print('AUDIT_PATH=PASS / CUSTOMER_ROW_WRITE=enrollment_learner+course_enrollment')
        return 0
    except (Stop,diag.Stop,base.Stop,ValueError,Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,(Stop,diag.Stop,base.Stop)):
            code=str(exc)
        elif isinstance(exc,ValueError):
            code=str(exc) or 'bootstrap_validation_failed'
        else:
            code=type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No secrets, identifiers or customer rows printed.',
              file=sys.stderr)
        return 1
    finally:
        runtime_url=None
        os.environ.pop('DATABASE_URL',None)


if __name__=='__main__':
    raise SystemExit(main())
