"""Canonical course entitlements in disposable localhost PostgreSQL only."""
from datetime import date, datetime, timedelta, timezone
import os
from uuid import UUID, uuid4

import pytest

import auth_core as core
import oauth_migrate,login_return_migrate,member_profile_migrate
import oauth_signup_profile_migrate,oauth_signup_demographics_migrate,kakao_ci_migrate
import course_domain_migrate,course_entitlement_migrate
import course_domain_models as model
import course_domain_store as store
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres, CONSENT
from test_monthly_postgres import monthly_db
from test_manual_postgres import registry_db

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture(scope='module')
def course_db(registry_db):
    assert oauth_migrate.apply_migration()
    assert login_return_migrate.apply_migration()
    assert member_profile_migrate.apply_migration()
    assert oauth_signup_profile_migrate.apply_migration()
    assert oauth_signup_demographics_migrate.apply_migration()
    assert kakao_ci_migrate.apply_migration()
    assert course_domain_migrate.apply_migration()
    assert course_entitlement_migrate.apply_migration()
    return registry_db


@pytest.fixture
def actors(course_db):
    admin=core.register_verified_identity(
        core.VerifiedIdentity('kakao','course-ci',uuid4().hex,'가상 운영자'),CONSENT)
    member=core.register_verified_identity(
        core.VerifiedIdentity('naver','course-ci',uuid4().hex,'같은 가상 이름'),CONSENT)
    with course_db() as c:
        c.execute("UPDATE richon.members SET role='admin' WHERE member_id=%s",(admin,))
    return admin,member


def req(): return uuid4()


def add_months(value,months):
    month=value.month-1+months
    year=value.year+month//12
    month=month%12+1
    # Tests use days <=28 to avoid end-of-month ambiguity.
    return date(year,month,value.day)


def program(admin,pid,mode='date_range',months=None):
    return store.mutate(admin,'program.create',model.ProgramCreate(
        request_id=req(),reason='가상 프로그램',program_id=pid,title='가상 '+pid,
        access_mode=mode,fixed_months=months))


def run(admin,pid,start,end,*,label='1기'):
    return store.mutate(admin,'run.create',model.RunCreate(
        request_id=req(),reason='가상 기수',program_id=pid,cohort_label=label,
        starts_on=start,ends_on=end,default_access_start=start,default_access_end=end,
        status='OPEN',price_krw=1000))


def test_migrations_reenter_and_no_legacy_drop(course_db):
    assert course_domain_migrate.apply_migration() is False
    assert course_entitlement_migrate.apply_migration() is False
    with course_db() as c:
        assert c.execute("SELECT count(*) FROM richon.schema_migrations WHERE version IN ('015_course_run_foundation','016_course_entitlements')").fetchone()==(2,)
        for table in ('courses','monthly_enrollments','manual_enrollments','course_programs','course_runs','course_enrollments'):
            assert c.execute('SELECT to_regclass(%s)',('richon.'+table,)).fetchone()[0] is not None


def test_pre_richon_fixed_two_month_entitlement_and_idempotency(course_db,actors):
    admin,member=actors
    pid='pre-'+uuid4().hex[:12];program(admin,pid,'fixed_months',2)
    start=date.today().replace(day=min(date.today().day,28))
    end=add_months(start,2)-timedelta(days=1)
    r=run(admin,pid,start,end)
    body=model.EnrollmentGrant(request_id=req(),reason='가상 수강권',run_id=UUID(r['run_id']),member_id=member)
    first=store.mutate(admin,'enrollment.grant',body)
    assert store.mutate(admin,'enrollment.grant',body)==first
    with course_db() as c:
        row=c.execute('SELECT access_start,access_end,source FROM richon.course_enrollments WHERE enrollment_id=%s',(first['enrollment_id'],)).fetchone()
        assert row==(start,end,'ADMIN')
    custom=model.EnrollmentGrant(request_id=req(),reason='가상 임의 기간',run_id=UUID(r['run_id']),member_id=member,
                                 access_start=start,access_end=end-timedelta(days=1))
    with pytest.raises(store.Rejected) as exc:store.mutate(admin,'enrollment.grant',custom)
    assert exc.value.code=='fixed_access_window'


def test_date_range_run_allows_admin_selected_period(course_db,actors):
    admin,member=actors
    pid='study-'+uuid4().hex[:10];program(admin,pid)
    start=date.today()-timedelta(days=10);end=date.today()+timedelta(days=100)
    r=run(admin,pid,start,end)
    access_start=date.today();access_end=date.today()+timedelta(days=30)
    grant=store.mutate(admin,'enrollment.grant',model.EnrollmentGrant(
        request_id=req(),reason='가상 기간제',run_id=UUID(r['run_id']),member_id=member,
        access_start=access_start,access_end=access_end,note='수기 등록'))
    with course_db() as c:
        assert c.execute('SELECT access_start,access_end,source,note FROM richon.course_enrollments WHERE enrollment_id=%s',
                         (grant['enrollment_id'],)).fetchone()==(access_start,access_end,'ADMIN','수기 등록')


def test_member_grant_never_auto_merges_same_name_guest(course_db,actors):
    admin,member=actors
    guest=uuid4()
    with course_db() as c:
        c.execute('INSERT INTO richon.enrollment_learners(learner_id,name,phone) VALUES(%s,%s,%s)',
                  (guest,'같은 가상 이름','01000000000'))
    pid='nomerge-'+uuid4().hex[:8];program(admin,pid)
    start=date.today();end=start+timedelta(days=20);r=run(admin,pid,start,end)
    out=store.mutate(admin,'enrollment.grant',model.EnrollmentGrant(
        request_id=req(),reason='가상 명시 회원',run_id=UUID(r['run_id']),member_id=member))
    assert out['learner_id']!=str(guest)
    with course_db() as c:
        assert c.execute('SELECT member_id FROM richon.enrollment_learners WHERE learner_id=%s',(out['learner_id'],)).fetchone()==(member,)
        assert c.execute('SELECT member_id FROM richon.enrollment_learners WHERE learner_id=%s',(guest,)).fetchone()==(None,)


def test_my_courses_exposes_optional_resources_only_during_access(course_db,actors):
    admin,member=actors
    pid='content-'+uuid4().hex[:8];program(admin,pid)
    start=date.today()-timedelta(days=1);end=date.today()+timedelta(days=30);r=run(admin,pid,start,end)
    created=store.mutate(admin,'session.create',model.SessionCreate(
        request_id=req(),reason='가상 회차',run_id=UUID(r['run_id']),sequence_no=1,title='첫 회차',
        mentor_name='가상 멘토',starts_at=datetime.now(timezone.utc)))
    rows=store.sessions(UUID(r['run_id']))
    assert rows[0]['video_url'] is None and rows[0]['material_url'] is None
    updated=store.mutate(admin,'session.update',model.SessionUpdate(
        request_id=req(),reason='가상 링크 추가',session_id=UUID(created['session_id']),version=created['version'],
        title='첫 회차',mentor_name='가상 멘토',starts_at=rows[0]['starts_at'],ends_at=rows[0]['ends_at'],
        video_url='https://example.invalid/video',material_url='https://example.invalid/material'))
    assert updated['version']==created['version']+1
    grant=store.mutate(admin,'enrollment.grant',model.EnrollmentGrant(
        request_id=req(),reason='가상 활성 수강',run_id=UUID(r['run_id']),member_id=member))
    own=store.my_courses(member,20,0)
    row=next(x for x in own['items'] if x['enrollment_id']==grant['enrollment_id'])
    assert row['status']=='ACTIVE'
    assert row['sessions'][0]['video_url']=='https://example.invalid/video'
    assert row['sessions'][0]['material_url']=='https://example.invalid/material'
    with course_db() as c:
        c.execute("UPDATE richon.course_enrollments SET status='SUSPENDED',suspended_at=CURRENT_TIMESTAMP WHERE enrollment_id=%s",
                  (grant['enrollment_id'],))
    hidden=store.my_courses(member,20,0)
    row=next(x for x in hidden['items'] if x['enrollment_id']==grant['enrollment_id'])
    assert row['status']=='SUSPENDED'
    assert row['sessions'][0]['video_url'] is None and row['sessions'][0]['material_url'] is None


def test_admin_cancel_is_audited_and_does_not_delete_history(course_db,actors):
    admin,member=actors
    pid='cancel-'+uuid4().hex[:8];program(admin,pid)
    start=date.today();end=start+timedelta(days=10);r=run(admin,pid,start,end)
    grant=store.mutate(admin,'enrollment.grant',model.EnrollmentGrant(
        request_id=req(),reason='가상 지급',run_id=UUID(r['run_id']),member_id=member))
    cancel=model.EnrollmentCancel(request_id=req(),reason='가상 취소',enrollment_id=UUID(grant['enrollment_id']),version=grant['version'])
    result=store.mutate(admin,'enrollment.cancel',cancel)
    assert result['status']=='CANCELLED'
    with course_db() as c:
        assert c.execute('SELECT status,cancelled_at IS NOT NULL FROM richon.course_enrollments WHERE enrollment_id=%s',(grant['enrollment_id'],)).fetchone()==('CANCELLED',True)
        assert c.execute("SELECT count(*) FROM richon.course_domain_audit WHERE operation IN ('enrollment.grant','enrollment.cancel') AND entity_id=%s",(grant['enrollment_id'],)).fetchone()==(2,)
