"""Full repository + disposable loopback PostgreSQL required. Not run in the handoff environment."""
from datetime import datetime,timezone
import os
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import auth_core as core
import auth_http as auth
import portal,portal_migrate,monthly_migrate
import monthly_portal as monthly
from main import invalid_request
from test_orders_postgres import postgres
from test_auth_postgres import auth_postgres,guarded_target,CONSENT,ORIGIN

pytestmark=pytest.mark.skipif(os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires the authorized disposable loopback richon_ci database')

@pytest.fixture(scope='module')
def monthly_db(auth_postgres):
    assert portal_migrate.apply_migration()
    assert monthly_migrate.apply_migration()
    return auth_postgres

@pytest.fixture
def sample(monthly_db,monkeypatch):
    run=uuid4().hex
    admin=core.register_verified_identity(core.VerifiedIdentity('kakao','monthly-test',uuid4().hex,'가상 운영자'),CONSENT)
    member=core.register_verified_identity(core.VerifiedIdentity('naver','monthly-test',uuid4().hex,'가상 회원'),CONSENT)
    with monthly_db() as c:c.execute("UPDATE richon.members SET role='admin' WHERE member_id=%s",(admin,))
    admin_session,member_session=core.issue_session(admin),core.issue_session(member)
    a,b=uuid4(),uuid4();e1,e2,e3=uuid4(),uuid4(),uuid4();c1,c2='month-'+run,'fixed-'+run
    with monthly_db() as c:
        for cid,title in [(c1,'가상 리치온'),(c2,'가상 프리리치온')]:
            c.execute('INSERT INTO richon.courses(course_id,title,cohort,price_krw) VALUES(%s,%s,%s,1000)',(cid,title,run))
        c.execute("INSERT INTO richon.course_month_rules VALUES(%s,'2026-10-01','monthly',NULL),(%s,'2026-10-01','fixed',2)",(c1,c2))
        c.execute('''INSERT INTO richon.enrollment_learners(learner_id,member_id,name,nickname,email,phone)
          VALUES(%s,%s,%s,%s,'synthetic@example.invalid','01000000000'),(%s,NULL,%s,%s,'synthetic@example.invalid','01000000000')''',
          (a,member,'가상A-'+run,'별명A-'+run,b,'가상B-'+run,'별명B-'+run))
        c.execute('INSERT INTO richon.monthly_enrollments(enrollment_id,learner_id,course_id) VALUES(%s,%s,%s),(%s,%s,%s),(%s,%s,%s)',(e1,a,c1,e2,b,c1,e3,a,c2))
    def term(e,seq,months,confirmed=True,price=1000,receipt='not_requested'):
        now=datetime.now(timezone.utc)
        with monthly_db() as c:
            c.execute('''INSERT INTO richon.monthly_enrollment_terms
              (term_id,enrollment_id,sequence_no,months,grant_state,confirmed_at,confirmation_ref,
               quoted_amount_krw,payment_state,paid_amount_krw,paid_at,payment_record_ref,receipt_state)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
              (uuid4(),e,seq,months,'confirmed' if confirmed else 'pending',now if confirmed else None,
               'synthetic-grant' if confirmed else None,price,'recorded' if confirmed else 'pending',
               price if confirmed else None,now if confirmed else None,'synthetic-payment' if confirmed else None,receipt))
    term(e1,1,3,price=240000);term(e1,2,1,price=90000);term(e1,3,12,False,800000,'requested')
    term(e2,1,1,False,90000,'requested');term(e3,1,2,price=150000)
    monkeypatch.setenv('RICHON_AUTH_ENABLED','true');monkeypatch.setenv('RICHON_PORTAL_ENABLED','true')
    monkeypatch.setenv('RICHON_MONTHLY_ENABLED','true');monkeypatch.setenv('RICHON_AUTH_ALLOWED_ORIGINS',ORIGIN)
    app=FastAPI();app.add_exception_handler(RequestValidationError,invalid_request)
    app.include_router(auth.make_router(auth.AuthSettings(frozenset({ORIGIN}))))
    portal.install_if_enabled(app);monthly.install_if_enabled(app)
    def client(token):return TestClient(app,base_url=ORIGIN,headers={'Cookie':auth.COOKIE+'='+token,'Origin':ORIGIN,'X-CSRF-Token':core.csrf_token(token)})
    def query(**kw):
        with client(admin_session.token) as c:
            r=c.post('/portal/api/admin/enrollments/search',json={'month':'2026-10','q':run,**kw})
            assert r.status_code==200,r.text
            return r.json()
    return dict(run=run,a=a,b=b,e1=e1,e2=e2,e3=e3,c1=c1,c2=c2,term=term,query=query,client=client,admin=admin,sa=admin_session,sm=member_session)


def test_reentry(monthly_db):assert monthly_migrate.apply_migration() is False

def test_no_duplicate_people_or_unpaid_extension(sample):
    d=sample['query']();s=d['summary']
    assert (s['total'],s['confirmed_people'],s['confirmed_enrollments'],s['pending_people'])==(3,1,2,2)
    row=next(x for x in d['items'] if x['enrollment_id']==str(sample['e1']))
    assert (row['start_month'],row['end_month'],row['confirmed_months'])==('2026-10','2027-01',4)
    assert row['pending_terms']==1 and row['net_recorded_paid_krw']==330000 and row['latest_quoted_krw']==800000

@pytest.mark.parametrize('month,people,enrollments,ending',[('2026-09',0,0,0),('2026-11',1,2,1),('2026-12',1,1,0),('2027-01',1,1,1),('2027-02',0,0,0)])
def test_boundaries(sample,month,people,enrollments,ending):
    s=sample['query'](month=month)['summary']
    assert (s['confirmed_people'],s['confirmed_enrollments'],s['ending_people'])==(people,enrollments,ending)

def test_fixed_two_months_and_immutable_history(monthly_db,sample):
    import psycopg
    with pytest.raises(psycopg.errors.RaiseException):sample['term'](sample['e3'],2,1)
    with pytest.raises(psycopg.errors.RaiseException):sample['term'](sample['e3'],2,2)
    with pytest.raises(psycopg.errors.RaiseException):
        with monthly_db() as c:c.execute("UPDATE richon.monthly_enrollment_terms SET months=12 WHERE enrollment_id=%s AND sequence_no=1",(sample['e1'],))
    with pytest.raises(psycopg.errors.RaiseException):
        with monthly_db() as c:c.execute('DELETE FROM richon.monthly_enrollment_terms WHERE enrollment_id=%s AND sequence_no=1',(sample['e1'],))

def test_combined_filters_same_purchase(sample):
    assert sample['query'](plan_months=3,payment_state='pending')['items']==[]
    d=sample['query'](plan_months=12,payment_state='pending',receipt_state='requested')
    assert [x['enrollment_id'] for x in d['items']]==[str(sample['e1'])]

def test_guest_contact_and_join_date(sample):
    d=sample['query'](course_id=sample['c1'],q='010-0000-0000')
    assert len(d['items'])==2
    assert all(x['phone_masked']=='010-****-0000' and x['email_masked']=='s***@example.invalid' for x in d['items'])
    guest=next(x for x in d['items'] if not x['member_linked'])
    assert guest['joined_at'] is None and guest['net_recorded_paid_krw'] is None

def test_pagination_summary(sample):
    a=sample['query'](limit=1,offset=0);b=sample['query'](limit=1,offset=1)
    assert a['summary']==b['summary'] and a['summary']['total']==3
    assert a['items'][0]['enrollment_id']!=b['items'][0]['enrollment_id']

@pytest.mark.parametrize('q',["%' OR TRUE; --",'%','_','\\'])
def test_literal_search(sample,q):assert sample['query'](q=q)['items']==[]

def test_confirmed_segments(sample):
    with sample['client'](sample['sa'].token) as c:
        r=c.get('/portal/api/admin/enrollments/'+str(sample['e1'])+'/terms')
        assert r.status_code==200
        pending,extension,first=r.json()['items']
        assert pending['end_month'] is None
        assert (extension['start_month'],extension['end_month'])==('2027-01','2027-01')
        assert (first['start_month'],first['end_month'])==('2026-10','2026-12')
        assert c.get('/portal/api/admin/enrollments/'+str(uuid4())+'/terms').status_code==404

def test_real_member_session_denied(sample):
    with sample['client'](sample['sm'].token) as c:
        assert c.get('/portal/api/admin/enrollments/options').status_code==403
        assert c.post('/portal/api/admin/enrollments/search',json={'month':'2026-10'}).status_code==403
        assert c.get('/portal/api/admin/enrollments/'+str(sample['e1'])+'/terms').status_code==403

def test_schema_failure_is_not_false_empty(monthly_db,sample):
    with monthly_db() as c:c.execute('ALTER TABLE richon.monthly_enrollment_terms RENAME TO monthly_hidden_terms')
    try:
        with sample['client'](sample['sa'].token) as c:
            r=c.post('/portal/api/admin/enrollments/search',json={'month':'2026-10'})
            assert r.status_code==503 and r.json()=={'detail':'monthly_store_unavailable'}
    finally:
        with monthly_db() as c:c.execute('ALTER TABLE richon.monthly_hidden_terms RENAME TO monthly_enrollment_terms')
