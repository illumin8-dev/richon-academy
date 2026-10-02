"""Canonical course entitlements in disposable localhost PostgreSQL only."""
from datetime import date, datetime, timedelta, timezone
import os
from uuid import UUID, uuid4

import pytest

import auth_core as core
import oauth_migrate,login_return_migrate,member_profile_migrate
import oauth_signup_profile_migrate,oauth_signup_demographics_migrate,kakao_ci_migrate
import course_domain_migrate,course_entitlement_migrate,course_adjustment_migrate,calendar_migrate,calendar_freeform_migrate
import course_domain_models as model
import course_domain_store as store
import portal
import portal_store
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
    assert course_adjustment_migrate.apply_migration()
    assert calendar_migrate.apply_migration()
    assert calendar_freeform_migrate.apply_migration()
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
    assert course_adjustment_migrate.apply_migration() is False
    assert calendar_migrate.apply_migration() is False
    assert calendar_freeform_migrate.apply_migration() is False
    with course_db() as c:
        assert c.execute("SELECT count(*) FROM richon.schema_migrations WHERE version IN ('015_course_run_foundation','016_course_entitlements','018_calendar_events','019_calendar_freeform','021_course_enrollment_adjustments')").fetchone()==(5,)
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
    row=next(x for x in own['items'] if str(x['enrollment_id'])==grant['enrollment_id'])
    assert row['status']=='ACTIVE'
    assert row['sessions'][0]['video_url']=='https://example.invalid/video'
    assert row['sessions'][0]['material_url']=='https://example.invalid/material'
    suspended=store.mutate(admin,'enrollment.suspend',model.EnrollmentSuspend(
        request_id=req(),reason='가상 콘텐츠 휴식',enrollment_id=UUID(grant['enrollment_id']),
        version=grant['version']))
    assert suspended['status']=='SUSPENDED'
    hidden=store.my_courses(member,20,0)
    row=next(x for x in hidden['items'] if str(x['enrollment_id'])==grant['enrollment_id'])
    assert row['status']=='SUSPENDED'
    assert row['sessions'][0]['video_url'] is None and row['sessions'][0]['material_url'] is None


def test_admin_cancel_restore_and_resume_are_audited_without_deleting_history(course_db,actors):
    admin,member=actors
    pid='cancel-'+uuid4().hex[:8];program(admin,pid)
    start=date.today();end=start+timedelta(days=10);r=run(admin,pid,start,end)
    grant=store.mutate(admin,'enrollment.grant',model.EnrollmentGrant(
        request_id=req(),reason='가상 지급',run_id=UUID(r['run_id']),member_id=member))

    cancel=model.EnrollmentCancel(
        request_id=req(),reason='가상 취소',enrollment_id=UUID(grant['enrollment_id']),version=grant['version'])
    cancelled=store.mutate(admin,'enrollment.cancel',cancel)
    assert cancelled['status']=='CANCELLED'
    restored=store.mutate(admin,'enrollment.restore',model.EnrollmentRestore(
        request_id=req(),reason='가상 복구',enrollment_id=UUID(grant['enrollment_id']),version=cancelled['version']))
    assert restored['status']=='ACTIVE'

    suspended=store.mutate(admin,'enrollment.suspend',model.EnrollmentSuspend(
        request_id=req(),reason='가상 휴식',enrollment_id=UUID(grant['enrollment_id']),version=restored['version']))
    assert suspended['status']=='SUSPENDED'
    resumed=store.mutate(admin,'enrollment.resume',model.EnrollmentResume(
        request_id=req(),reason='가상 재개',enrollment_id=UUID(grant['enrollment_id']),version=suspended['version']))
    assert resumed['status']=='ACTIVE'

    with pytest.raises(store.Rejected) as exc:
        store.mutate(admin,'enrollment.restore',model.EnrollmentRestore(
            request_id=req(),reason='활성 수강권 중복 복구',enrollment_id=UUID(grant['enrollment_id']),version=resumed['version']))
    assert exc.value.code=='enrollment_not_restorable'

    with course_db() as c:
        assert c.execute('''SELECT status,cancelled_at,suspended_at
            FROM richon.course_enrollments WHERE enrollment_id=%s''',(grant['enrollment_id'],)).fetchone()==('ACTIVE',None,None)
        adjustments=c.execute('''SELECT kind,status_before,status_after,access_end_before,access_end_after
            FROM richon.course_enrollment_adjustments WHERE enrollment_id=%s ORDER BY created_at,adjustment_id''',
            (grant['enrollment_id'],)).fetchall()
        assert [x[:3] for x in adjustments]==[
            ('SUSPEND','ACTIVE','SUSPENDED'),('RESUME','SUSPENDED','ACTIVE')]
        assert all(x[3]==x[4]==end for x in adjustments)
        assert c.execute("""SELECT count(*) FROM richon.course_domain_audit
            WHERE operation IN ('enrollment.grant','enrollment.cancel','enrollment.restore',
                                'enrollment.suspend','enrollment.resume')
              AND entity_id=%s""",(grant['enrollment_id'],)).fetchone()==(5,)


def test_extend_and_refund_preserve_history_and_idempotency(course_db,actors):
    admin,member=actors
    pid='adjust-'+uuid4().hex[:8];program(admin,pid)
    start=date.today();end=start+timedelta(days=30);r=run(admin,pid,start,end)
    grant=store.mutate(admin,'enrollment.grant',model.EnrollmentGrant(
        request_id=req(),reason='가상 조정 지급',run_id=UUID(r['run_id']),member_id=member))

    extend_body=model.EnrollmentExtend(
        request_id=req(),reason='운영 일정 보상 무료 연장',enrollment_id=UUID(grant['enrollment_id']),
        version=grant['version'],new_access_end=end+timedelta(days=10),extension_kind='FREE')
    extended=store.mutate(admin,'enrollment.extend',extend_body)
    assert extended['access_end']==str(end+timedelta(days=10))
    assert store.mutate(admin,'enrollment.extend',extend_body)==extended

    partial=store.mutate(admin,'enrollment.refund',model.EnrollmentRefund(
        request_id=req(),reason='일부 수강분 환불',enrollment_id=UUID(grant['enrollment_id']),
        version=extended['version'],refund_kind='PARTIAL',refund_amount_krw=50000,
        refund_reference='synthetic-partial',new_access_end=end+timedelta(days=5)))
    assert partial['refund_kind']=='PARTIAL'
    assert partial['access_end']==str(end+timedelta(days=5))

    full=store.mutate(admin,'enrollment.refund',model.EnrollmentRefund(
        request_id=req(),reason='잔여 전액 환불',enrollment_id=UUID(grant['enrollment_id']),
        version=partial['version'],refund_kind='FULL',refund_amount_krw=100000,
        refund_reference='synthetic-full'))
    assert full['status']=='CANCELLED'

    history=store.adjustments(UUID(grant['enrollment_id']))
    assert [x['kind'] for x in history]==['REFUND','REFUND','EXTEND']
    assert history[0]['refund_kind']=='FULL' and history[0]['refund_amount_krw']==100000
    assert history[1]['refund_kind']=='PARTIAL' and history[1]['access_end_after']==end+timedelta(days=5)
    assert history[2]['extension_kind']=='FREE' and history[2]['access_end_after']==end+timedelta(days=10)

    with course_db() as db:
        assert db.execute('SELECT count(*) FROM richon.course_enrollment_adjustments WHERE enrollment_id=%s',
                          (grant['enrollment_id'],)).fetchone()==(3,)
        assert db.execute('SELECT status,access_end,cancelled_at IS NOT NULL FROM richon.course_enrollments WHERE enrollment_id=%s',
                          (grant['enrollment_id'],)).fetchone()==('CANCELLED',end+timedelta(days=5),True)


def test_resume_can_extend_only_with_explicit_free_or_paid_kind(course_db,actors):
    admin,member=actors
    pid='resume-'+uuid4().hex[:8];program(admin,pid)
    start=date.today();end=start+timedelta(days=14);r=run(admin,pid,start,end)
    grant=store.mutate(admin,'enrollment.grant',model.EnrollmentGrant(
        request_id=req(),reason='가상 재개 연장 지급',run_id=UUID(r['run_id']),member_id=member))
    suspended=store.mutate(admin,'enrollment.suspend',model.EnrollmentSuspend(
        request_id=req(),reason='가상 휴식',enrollment_id=UUID(grant['enrollment_id']),version=grant['version']))
    resumed=store.mutate(admin,'enrollment.resume',model.EnrollmentResume(
        request_id=req(),reason='휴식 보상 연장 재개',enrollment_id=UUID(grant['enrollment_id']),
        version=suspended['version'],new_access_end=end+timedelta(days=7),extension_kind='FREE'))
    assert resumed['status']=='ACTIVE' and resumed['access_end']==str(end+timedelta(days=7))
    history=store.adjustments(UUID(grant['enrollment_id']))
    assert history[0]['kind']=='RESUME' and history[0]['extension_kind']=='FREE'
    assert history[0]['access_end_before']==end
    assert history[0]['access_end_after']==end+timedelta(days=7)


def test_admin_member_detail_combines_canonical_enrollment_with_legacy_enabled(course_db,actors,monkeypatch):
    admin,member=actors
    pid='detail-'+uuid4().hex[:8]
    program(admin,pid)
    start=date.today()
    end=start+timedelta(days=30)
    r=run(admin,pid,start,end,label='상세 테스트')
    grant=store.mutate(admin,'enrollment.grant',model.EnrollmentGrant(
        request_id=req(),reason='가상 회원 상세',run_id=UUID(r['run_id']),member_id=member))
    monkeypatch.setenv('RICHON_MONTHLY_ENABLED','true')
    detail=portal_store.member_detail(member)
    validated=portal.AdminMemberDetail.model_validate(detail)
    row=next(x for x in validated.learning if str(x.enrollment_id)==grant['enrollment_id'])
    assert row.program_title=='가상 '+pid
    assert row.cohort_label=='상세 테스트'
    assert validated.legacy_learning==[]
    assert validated.orders==[]


def test_public_calendar_filters_private_rows_and_reports_adjacent_months(course_db,actors):
    admin,_=actors
    june=store.mutate(admin,'calendar_event.create',model.CalendarEventCreate(
        request_id=req(),reason='공개 이전달',event_date=date(2026,6,29),
        color_hex='#D8BD78',course_label='리치온 아카데미',content_text='무료 브리핑'))
    july=store.mutate(admin,'calendar_event.create',model.CalendarEventCreate(
        request_id=req(),reason='공개 현재달',event_date=date(2026,7,1),
        color_hex='#FF9F26',course_label='리치온 인테리어'))
    august=store.mutate(admin,'calendar_event.create',model.CalendarEventCreate(
        request_id=req(),reason='공개 다음달',event_date=date(2026,8,6),
        color_hex='#00B622',course_label='Pre리치온',content_text='부동산 투자원칙'))
    with course_db() as cur:
        cur.execute('UPDATE richon.calendar_events SET is_public=FALSE WHERE event_id=%s',(UUID(july['event_id']),))
    data=store.public_calendar(
        datetime(2026,5,31,15,tzinfo=timezone.utc),
        datetime(2026,6,30,15,tzinfo=timezone.utc),
        datetime(2026,7,31,15,tzinfo=timezone.utc),
        datetime(2026,8,31,15,tzinfo=timezone.utc))
    assert data['items']==[]
    assert data['has_prev'] is True and data['has_next'] is True


def test_visual_calendar_event_banner_update_delete_and_overlap(course_db,actors):
    admin,_=actors
    created=store.mutate(admin,'calendar_event.create',model.CalendarEventCreate(
        request_id=req(),reason='가상 일정',event_date=date(2026,10,8),
        color_hex='#00B622',course_label='Pre리치온',content_text='부동산 투자원칙'))
    rows=store.admin_calendar(datetime(2026,9,30,15,tzinfo=timezone.utc),datetime(2026,10,31,15,tzinfo=timezone.utc))
    row=next(x for x in rows if str(x['event_id'])==created['event_id'])
    assert (row['display_kind'],row['event_date'],row['end_date'])==('EVENT','2026-10-08',None)
    assert (row['color_hex'],row['course_label'],row['content_text'])==('#00B622','Pre리치온','부동산 투자원칙')

    updated=store.mutate(admin,'calendar_event.update',model.CalendarEventUpdate(
        request_id=req(),reason='가상 수정',event_id=UUID(created['event_id']),version=created['version'],
        event_date=date(2026,10,21),color_hex='#C000DB',
        course_label='자유 과정',content_text='원하는 날짜로 이동'))
    assert updated['version']==created['version']+1

    banner=store.mutate(admin,'calendar_event.create',model.CalendarEventCreate(
        request_id=req(),reason='가상 연휴',display_kind='BANNER',
        event_date=date(2026,9,29),end_date=date(2026,10,2),
        color_hex='#FF5757',course_label='연휴'))
    october=store.admin_calendar(datetime(2026,9,30,15,tzinfo=timezone.utc),datetime(2026,10,31,15,tzinfo=timezone.utc))
    holiday=next(x for x in october if str(x['event_id'])==banner['event_id'])
    assert (holiday['display_kind'],holiday['event_date'],holiday['end_date'])==('BANNER','2026-09-29','2026-10-02')
    assert holiday['content_text']==''

    deleted=store.mutate(admin,'calendar_event.update',model.CalendarEventUpdate(
        request_id=req(),reason='가상 삭제',event_id=UUID(created['event_id']),version=updated['version'],
        event_date=date(2026,10,21),color_hex='#C000DB',
        course_label='자유 과정',content_text='원하는 날짜로 이동',deleted=True))
    assert deleted['deleted'] is True
    rows=store.admin_calendar(datetime(2026,9,30,15,tzinfo=timezone.utc),datetime(2026,10,31,15,tzinfo=timezone.utc))
    assert all(str(x['event_id'])!=created['event_id'] for x in rows)
