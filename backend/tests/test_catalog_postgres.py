"""Catalog migration/API tests use only the disposable loopback PostgreSQL CI database."""
import os
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import auth_core as core,auth_http as auth
import portal,catalog_portal,catalog_migrate
from main import invalid_request
from test_auth_postgres import CONSENT,ORIGIN
from test_monthly_postgres import monthly_db

pytestmark=pytest.mark.skipif(os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires disposable loopback richon_ci')

@pytest.fixture(scope='module')
def catalog_db(monthly_db):
    assert catalog_migrate.apply_migration()
    return monthly_db

@pytest.fixture
def setup(catalog_db,monkeypatch):
    admin=core.register_verified_identity(core.VerifiedIdentity('kakao','catalog-ci',uuid4().hex,'가상 운영자'),CONSENT)
    member=core.register_verified_identity(core.VerifiedIdentity('naver','catalog-ci',uuid4().hex,'가상 회원'),CONSENT)
    with catalog_db() as c:c.execute("UPDATE richon.members SET role='admin' WHERE member_id=%s",(admin,))
    sa,sm=core.issue_session(admin),core.issue_session(member)
    monkeypatch.setenv('RICHON_AUTH_ENABLED','true')
    monkeypatch.setenv('RICHON_PORTAL_ENABLED','true')
    monkeypatch.setenv('RICHON_CATALOG_ENABLED','true')
    monkeypatch.setenv('RICHON_AUTH_ALLOWED_ORIGINS',ORIGIN)
    app=FastAPI();app.add_exception_handler(RequestValidationError,invalid_request)
    app.include_router(auth.make_router(auth.AuthSettings(frozenset({ORIGIN}))))
    portal.install_if_enabled(app);catalog_portal.install_if_enabled(app)
    def client(session):
        return TestClient(app,base_url=ORIGIN,headers={'Cookie':auth.COOKIE+'='+session.token,
            'Origin':ORIGIN,'X-CSRF-Token':core.csrf_token(session.token)})
    return {'admin':admin,'member':member,'sa':sa,'sm':sm,'client':client}

def post(c,path,body):
    return c.post('/portal/api/admin/catalog/'+path,json=body)

def program(c,kind='fixed_months',months=2,title='가상 프리리치온'):
    body={'request_id':str(uuid4()),'reason':'가상 과정 등록','title':title,'access_kind':kind}
    if months is not None:body['fixed_months']=months
    r=post(c,'programs',body);assert r.status_code==200,r.text
    return r.json(),body

def run(c,pid,*,start='2026-10-01',end='2026-11-30',access_start='2026-10-01',access_end='2026-11-30'):
    body={'request_id':str(uuid4()),'reason':'가상 기수 등록','program_id':pid,'cohort':'2026-10',
          'status':'OPEN','starts_on':start,'ends_on':end,'default_access_start':access_start,
          'default_access_end':access_end,'capacity':40,'price_krw':0}
    r=post(c,'runs',body);assert r.status_code==200,r.text
    return r.json(),body

def test_migration_reentry(catalog_db):
    assert catalog_migrate.apply_migration() is False

def test_fixed_two_month_program_run_and_weekly_session(setup):
    with setup['client'](setup['sa']) as c:
        p,pbody=program(c)
        r,rbody=run(c,p['program_id'])
        sbody={'request_id':str(uuid4()),'reason':'가상 1주차','run_id':r['run_id'],'sequence_no':1,
               'title':'시장 흐름','mentor_name':'이루민','starts_at':'2026-10-07T20:00:00+09:00',
               'ends_at':'2026-10-07T22:00:00+09:00','content_url':'https://example.invalid/week1'}
        s=post(c,'sessions',sbody);assert s.status_code==200,s.text
        sessions=c.get('/portal/api/admin/catalog/runs/'+r['run_id']+'/sessions')
        assert sessions.status_code==200 and sessions.json()[0]['mentor_name']=='이루민'
        programs=c.get('/portal/api/admin/catalog/programs').json()
        assert any(x['program_id']==p['program_id'] and x['fixed_months']==2 for x in programs)
        runs=c.get('/portal/api/admin/catalog/runs',params={'program_id':p['program_id']}).json()
        assert runs[0]['status']=='OPEN' and runs[0]['default_access_end']=='2026-11-30'

def test_fixed_period_mismatch_rejected_before_write(setup,catalog_db):
    with setup['client'](setup['sa']) as c:
        p,_=program(c)
        before=None
        with catalog_db() as db:before=db.execute('SELECT count(*) FROM richon.course_runs').fetchone()[0]
        body={'request_id':str(uuid4()),'reason':'가상 잘못된 기간','program_id':p['program_id'],'cohort':'bad',
              'status':'UPCOMING','starts_on':'2026-10-01','ends_on':'2026-12-31',
              'default_access_start':'2026-10-01','default_access_end':'2026-12-31','price_krw':0}
        bad=post(c,'runs',body)
        assert bad.status_code==422 and bad.json()['detail']=='fixed_access_period_mismatch'
        with catalog_db() as db:assert db.execute('SELECT count(*) FROM richon.course_runs').fetchone()[0]==before

def test_date_range_program_supports_arbitrary_period(setup):
    with setup['client'](setup['sa']) as c:
        p,_=program(c,'date_range',None,'가상 리치온')
        r,_=run(c,p['program_id'],end='2027-09-30',access_end='2027-09-30')
        row=c.get('/portal/api/admin/catalog/runs',params={'program_id':p['program_id']}).json()[0]
        assert row['run_id']==r['run_id'] and row['default_access_end']=='2027-09-30'

def test_idempotency_and_optimistic_version(setup):
    with setup['client'](setup['sa']) as c:
        p,body=program(c)
        assert post(c,'programs',body).json()==p
        changed={**body,'title':'다른 제목'}
        assert post(c,'programs',changed).status_code==409
        update={**body,'request_id':str(uuid4()),'program_id':p['program_id'],'version':p['version'],
                'title':'수정된 프리리치온','archived':False}
        ok=post(c,'programs/update',update);assert ok.status_code==200
        update['request_id']=str(uuid4())
        assert post(c,'programs/update',update).status_code==409

def test_access_policy_freezes_after_run_exists(setup):
    with setup['client'](setup['sa']) as c:
        p,body=program(c);run(c,p['program_id'])
        update={**body,'request_id':str(uuid4()),'program_id':p['program_id'],'version':1,
                'access_kind':'date_range','fixed_months':None,'archived':False}
        r=post(c,'programs/update',update)
        assert r.status_code==409 and r.json()['detail']=='program_access_policy_in_use'

def test_run_enrollment_trigger_enforces_fixed_months(setup,catalog_db):
    with setup['client'](setup['sa']) as c:
        p,_=program(c);r,_=run(c,p['program_id'])
    learner=uuid4()
    with catalog_db() as db:
        db.execute("INSERT INTO richon.enrollment_learners(learner_id,name) VALUES(%s,'가상 수강생')",(learner,))
        db.execute("""INSERT INTO richon.run_enrollments
          (enrollment_id,learner_id,run_id,access_start,access_end,status,source,created_by)
          VALUES(%s,%s,%s,'2026-10-01','2026-11-30','SCHEDULED','complimentary',%s)""",
          (uuid4(),learner,r['run_id'],setup['admin']))
    import psycopg
    with pytest.raises(psycopg.errors.RaiseException):
        with catalog_db() as db:
            db.execute("""INSERT INTO richon.run_enrollments
              (enrollment_id,learner_id,run_id,access_start,access_end,status,source,created_by)
              VALUES(%s,%s,%s,'2026-12-01','2027-02-28','SCHEDULED','manual',%s)""",
              (uuid4(),uuid4(),r['run_id'],setup['admin']))

def test_non_admin_cannot_read_or_mutate(setup):
    with setup['client'](setup['sm']) as c:
        assert c.get('/portal/api/admin/catalog/programs').status_code==403
        body={'request_id':str(uuid4()),'reason':'가상 권한 검사','title':'금지','access_kind':'date_range'}
        assert post(c,'programs',body).status_code==403
