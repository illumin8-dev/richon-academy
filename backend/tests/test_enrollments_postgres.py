"""Real SQL coverage in the existing guarded disposable CI database ONLY."""
import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import auth_core as core
import auth_http as http
import enrollments as api
import enrollment_store as store
import enrollment_migrate as migrate
from main import invalid_request
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres, CONSENT, ORIGIN
from test_portal_postgres import portal_postgres

pytestmark=pytest.mark.skipif(os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'), reason='Requires guarded disposable loopback richon_ci')


@pytest.fixture(scope='module')
def enrollment_db(portal_postgres):
    assert migrate.apply_migration()
    return portal_postgres


@pytest.fixture
def seed(enrollment_db):
    def make(*,start=date(2026,10,1),months=(1,),statuses=None,member=None,learner=None,course=None,receipt=True):
        course=course or 'enroll-'+uuid4().hex
        learner=learner or uuid4();eid=uuid4()
        with enrollment_db() as conn:
            if not conn.execute('SELECT 1 FROM richon.courses WHERE course_id=%s',(course,)).fetchone():
                conn.execute("INSERT INTO richon.courses (course_id,title,cohort,price_krw) VALUES (%s,'가상 수업','가상 기수',1000)",(course,))
                conn.execute('INSERT INTO richon.course_schedules (course_id,starts_on) VALUES (%s,%s)',(course,start))
            if not conn.execute('SELECT 1 FROM richon.learner_profiles WHERE learner_id=%s',(learner,)).fetchone():
                conn.execute("INSERT INTO richon.learner_profiles (learner_id,member_id,full_name,nickname,email,phone) VALUES (%s,%s,'같은 가상 이름','가상_별명','student@example.invalid','01000000000')",(learner,member))
            conn.execute('INSERT INTO richon.course_enrollments (enrollment_id,learner_id,course_id,starts_on) VALUES (%s,%s,%s,%s)',(eid,learner,course,start))
            for i,m in enumerate(months):
                state=(statuses or ['confirmed']*len(months))[i]
                conn.execute("""INSERT INTO richon.enrollment_terms
                  (term_id,enrollment_id,sequence,months,list_amount_krw,agreed_amount_krw,status,confirmed_at,cash_receipt_requested)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='confirmed' THEN CURRENT_TIMESTAMP ELSE NULL END,%s)""",
                  (uuid4(),eid,i+1,m,m*1000,m*900,state,state,receipt))
        return dict(eid=eid,learner=learner,course=course,member=member,start=start)
    return make


def query(e,**kwargs):
    return api.Filters(course_id=e['course'],**kwargs)


def one(e,as_of=date(2026,10,15),**kwargs):
    result=store.overview(query(e,**kwargs),as_of)
    return next(row for row in result['items'] if row['enrollment_id']==e['eid'])


def test_schema_reentry_does_not_change_orders(enrollment_db):
    with enrollment_db() as c: before=c.execute('SELECT count(*) FROM richon.orders').fetchone()
    assert migrate.apply_migration() is False
    with enrollment_db() as c: assert c.execute('SELECT count(*) FROM richon.orders').fetchone()==before


@pytest.mark.parametrize('start,months,expected',[
    (date(2026,10,1),(1,),date(2026,10,31)),
    (date(2026,10,1),(3,),date(2026,12,31)),
    (date(2026,10,1),(12,),date(2027,9,30)),
    (date(2026,10,15),(1,3),date(2027,2,14)),
    (date(2026,12,1),(3,),date(2027,2,28)),
    (date(2028,2,1),(1,),date(2028,2,29)),
    (date(2026,1,31),(1,1),date(2026,3,30)),
])
def test_calendar_months_and_original_anchor(enrollment_db,seed,start,months,expected):
    e=seed(start=start,months=months);item=one(e)
    assert item['ends_on']==expected and item['total_months']==sum(months)
    assert item['calendar_review_required'] is False


@pytest.mark.parametrize('start,months',[(date(2026,1,31),(1,)),(date(2028,2,29),(12,)),(date(2026,3,31),(1,))])
def test_month_end_policy_is_not_guessed(enrollment_db,seed,start,months):
    e=seed(start=start,months=months);item=one(e)
    assert item['ends_on'] is None and item['enrollment_status']=='needs_review'
    assert item['calendar_review_required'] is True


@pytest.mark.parametrize('today,expected,remaining',[
    (date(2026,9,30),'scheduled',32),(date(2026,10,1),'active',31),
    (date(2026,10,31),'active',1),(date(2026,11,1),'ended',0),
])
def test_status_uses_course_start_not_payment_or_signup(enrollment_db,seed,today,expected,remaining):
    e=seed();row=one(e,today)
    assert row['enrollment_status']==expected and row['remaining_days']==remaining


def test_pending_or_cancelled_extension_does_not_extend(enrollment_db,seed):
    e=seed(months=(1,3,12),statuses=['confirmed','pending','cancelled'])
    row=one(e)
    assert row['total_months']==1 and row['ends_on']==date(2026,10,31)
    assert row['latest_plan_months']==3 and row['pending_term_count']==1


def test_no_confirmed_term_is_not_a_student(enrollment_db,seed):
    e=seed(statuses=['pending']);result=store.overview(query(e),date(2026,10,15))
    assert result['items'][0]['enrollment_status']=='pending'
    assert result['summary']['active_learners']==0


def test_each_extension_adds_months_without_duplicate_enrollment(enrollment_db,seed):
    e=seed(months=(1,3,12));row=one(e)
    result=store.overview(query(e),date(2026,10,15))
    assert row['total_months']==16 and row['ends_on']==date(2028,1,31)
    assert result['summary']['active_learners']==1 and result['summary']['enrollment_count']==1


def test_people_count_deduplicates_across_courses_not_by_contact(enrollment_db,seed):
    a=seed();b=seed(learner=a['learner']);other=seed(course=a['course'])
    filters=api.Filters(q=str(a['learner']))
    result=store.overview(filters,date(2026,10,15))
    assert result['summary']['enrollment_count']==2 and result['summary']['active_learners']==1
    assert len(result['courses'])==2 and all(c['active_learners']==1 for c in result['courses'])
    same_course=store.overview(query(a),date(2026,10,15))
    assert same_course['summary']['active_learners']==2


def test_filtered_summary_not_current_page_only(enrollment_db,seed):
    a=seed();seed(course=a['course']);seed(course=a['course'])
    r=store.overview(query(a,limit=1),date(2026,10,26))
    assert len(r['items'])==1 and r['has_more'] is True
    assert r['summary']['enrollment_count']==3 and r['summary']['ending_soon']==3
    r2=store.overview(query(a,limit=1,offset=1),date(2026,10,26))
    assert r['items'][0]['enrollment_id']!=r2['items'][0]['enrollment_id']


def test_filter_intersection_and_masked_contacts(enrollment_db,seed):
    e=seed(months=(3,),receipt=True)
    r=store.overview(query(e,q='010-0000-0000',months=3,status='active',receipt='requested',end_from=date(2026,12,1),end_to=date(2026,12,31)),date(2026,10,15))
    assert r['summary']['enrollment_count']==1
    row=r['items'][0];assert row['phone_masked']=='010-****-0000' and row['email_masked']=='s***@example.invalid'
    assert 'student@example.invalid' not in str(r) and '01000000000' not in str(r)
    assert store.overview(query(e,months=1),date(2026,10,15))['items']==[]
    assert store.overview(query(e,receipt='unknown'),date(2026,10,15))['items']==[]
    assert store.overview(query(e,q="' OR 1=1 --"),date(2026,10,15))['items']==[]
    assert store.overview(query(e,q='%'),date(2026,10,15))['items']==[]


def test_paid_and_receipt_issued_are_never_faked(enrollment_db,seed):
    e=seed(months=(3,));row=one(e)
    assert row['latest_agreed_amount_krw']==2700 and row['latest_discount_krw']==300
    assert row['paid_amount_krw'] is None and row['payment_status']=='not_connected'
    assert row['cash_receipt_requested'] is True and row['cash_receipt_status']=='unverified'
    assert row['joined_at'] is None  # A guest is not given a fake signup date.


def test_price_changes_do_not_rewrite_existing_term_snapshots(enrollment_db,seed):
    e=seed(months=(3,));old=one(e)['latest_agreed_amount_krw']
    with enrollment_db() as c:
        c.execute('INSERT INTO richon.course_monthly_prices (course_id,months,list_amount_krw,sale_amount_krw) VALUES (%s,3,9000,8000)',(e['course'],))
    assert one(e)['latest_agreed_amount_krw']==old


def test_same_course_schedule_is_enforced(enrollment_db,seed):
    import psycopg
    e=seed()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with enrollment_db() as c:
            c.execute("UPDATE richon.course_enrollments SET starts_on=DATE '2026-10-02' WHERE enrollment_id=%s",(e['eid'],))


def test_admin_and_member_real_sessions(enrollment_db,seed):
    def member(role):
        mid=core.register_verified_identity(core.VerifiedIdentity('kakao','enroll-test',uuid4().hex,'가상 이름'),CONSENT)
        if role=='admin':
            with enrollment_db() as c: c.execute("UPDATE richon.members SET role='admin' WHERE member_id=%s",(mid,))
        return mid,core.issue_session(mid)
    mid,session=member('member');other,_=member('member');admin,ads=member('admin')
    a=seed(member=mid);b=seed(member=other,course=a['course']);guest=seed(course=a['course'])
    app=FastAPI();app.add_exception_handler(RequestValidationError,invalid_request);app.include_router(api.make_router())
    cookie=lambda t:{'Cookie':f'{http.COOKIE}={t}'}
    with TestClient(app,base_url=ORIGIN) as client:
        assert client.get('/portal/api/admin/enrollments',headers=cookie(session.token)).status_code==403
        response=client.get('/portal/api/me/enrollments',headers=cookie(session.token))
        assert response.status_code==200 and len(response.json()['items'])==1
        assert response.json()['items'][0]['enrollment_id']==str(a['eid'])
        assert str(b['eid']) not in response.text and str(guest['eid']) not in response.text
        assert response.json()['items'][0]['joined_at'] is not None
        r=client.get('/portal/api/admin/enrollments',params={'course_id':a['course']},headers=cookie(ads.token))
        assert r.status_code==200 and len(r.json()['items'])==3
        core.revoke_all_sessions(admin)
        assert client.get('/portal/api/admin/enrollments',headers=cookie(ads.token)).status_code==401
