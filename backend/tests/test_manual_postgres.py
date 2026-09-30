"""Manual CRUD in the existing disposable localhost CI DB, never Neon."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import auth_core as core,auth_http as auth
import portal,monthly_portal,manual_portal,manual_migrate,manual_store
import manual_models as model
from main import invalid_request
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target,auth_postgres,CONSENT,ORIGIN
from test_monthly_postgres import monthly_db
pytestmark=pytest.mark.skipif(os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),reason='Requires disposable loopback richon_ci')

@pytest.fixture(scope='module')
def registry_db(monthly_db):
    assert manual_migrate.apply_migration()
    return monthly_db

@pytest.fixture
def setup(registry_db,monkeypatch):
    actor=core.register_verified_identity(core.VerifiedIdentity('kakao','manual-ci',uuid4().hex,'가상 운영자'),CONSENT)
    with registry_db() as c:c.execute("UPDATE richon.members SET role='admin' WHERE member_id=%s",(actor,))
    session=core.issue_session(actor)
    for key in ['AUTH','PORTAL','MONTHLY','MANUAL']:monkeypatch.setenv('RICHON_'+key+'_ENABLED','true')
    monkeypatch.setenv('RICHON_AUTH_ALLOWED_ORIGINS',ORIGIN)
    a=FastAPI();a.add_exception_handler(RequestValidationError,invalid_request)
    a.include_router(auth.make_router(auth.AuthSettings(frozenset({ORIGIN}))))
    portal.install_if_enabled(a);monthly_portal.install_if_enabled(a);manual_portal.install_if_enabled(a)
    client=TestClient(a,base_url=ORIGIN,headers={'Cookie':auth.COOKIE+'='+session.token,'Origin':ORIGIN,'X-CSRF-Token':core.csrf_token(session.token)})
    return actor,client

def term(months=3,confirmed=True):
    return {'months':months,'confirmed':confirmed,'applied_on':'2026-09-22','payment_state':'recorded' if confirmed else 'pending',
       'quoted_amount_krw':1000,'paid_amount_krw':1000 if confirmed else None,'paid_on':'2026-09-20' if confirmed else None,
       'payment_ref':'synthetic-reference' if confirmed else None,'receipt_state':'not_requested'}

def call(client,path,body):
    return client.post('/portal/api/admin/manual/'+path,json=body)

def course(client,kind='monthly'):
    r=call(client,'courses',{'request_id':str(uuid4()),'reason':'가상 테스트','title':'가상 과정 '+uuid4().hex,'start_month':'2026-10','duration_kind':kind,'price_krw':1000})
    assert r.status_code==200,r.text
    assert r.json()['enabled'] is False
    return r.json()['course_id']

def create_body(cid,months=3,confirmed=True):
    return {'request_id':str(uuid4()),'reason':'가상 이전 명단','course_id':cid,
            'profile':{'name':'가상_'+uuid4().hex,'nickname':'가상 닉네임','phone':'010-0000-0000','email':'manual@example.invalid','original_joined_on':'2026-08-01'},'term':term(months,confirmed)}

def detail(client,eid):
    r=call(client,'read',{'enrollment_id':eid});assert r.status_code==200,r.text;return r.json()

def create(client,cid=None,months=3,confirmed=True):
    body=create_body(cid or course(client),months,confirmed);r=call(client,'create',body);assert r.status_code==200,r.text;return r.json(),body


def test_migration_reentry(registry_db):assert manual_migrate.apply_migration() is False

def test_create_does_not_create_login_or_pg_order(setup,registry_db):
    actor,c=setup
    sql='SELECT (SELECT count(*) FROM richon.members),(SELECT count(*) FROM richon.orders)'
    with registry_db() as db:before=db.execute(sql).fetchone()
    out,body=create(c);d=detail(c,out['enrollment_id'])
    assert d['original_joined_on']=='2026-08-01' and d['phone']=='01000000000'
    assert d['terms'][0]['grant_state']=='confirmed'
    with registry_db() as db:
        assert db.execute(sql).fetchone()==before
        assert db.execute('SELECT member_id FROM richon.enrollment_learners WHERE learner_id=%s',(out['learner_id'],)).fetchone()==(None,)
        assert db.execute('SELECT count(*) FROM richon.manual_audit WHERE entity_id=%s AND operation=%s',(out['enrollment_id'],'detail.read')).fetchone()==(1,)

def test_idempotency_and_changed_request_conflict(setup,registry_db):
    _,c=setup;out,body=create(c)
    assert call(c,'create',body).json()==out
    body['term']['months']=12
    assert call(c,'create',body).status_code==409
    with registry_db() as db:assert db.execute('SELECT count(*) FROM richon.manual_audit WHERE request_id=%s',(body['request_id'],)).fetchone()==(1,)

def test_duplicate_simultaneous_request_creates_one_record(setup,registry_db):
    actor,c=setup;body=model.Create(**create_body(course(c)));barrier=Barrier(4)
    def once(_):barrier.wait(timeout=10);return manual_store.mutate(actor,'create',body)
    with ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(once,range(4)))
    assert len({x['enrollment_id'] for x in result})==1

def test_profile_update_optimistic_version_and_no_automatic_merge(setup):
    _,c=setup;out,body=create(c);d=detail(c,out['enrollment_id'])
    update={'request_id':str(uuid4()),'reason':'가상 오타 정정','enrollment_id':out['enrollment_id'],'version':d['version'],'learner_version':d['learner_version'],'profile':{**body['profile'],'nickname':'수정된 가상 닉네임'}}
    assert call(c,'profile',update).status_code==200
    assert detail(c,out['enrollment_id'])['nickname']=='수정된 가상 닉네임'
    update['request_id']=str(uuid4());assert call(c,'profile',update).status_code==409
    other=call(c,'create',{**body,'request_id':str(uuid4())});assert other.status_code==200
    assert other.json()['learner_id']!=out['learner_id']

def test_explicit_learner_reuse_across_courses(setup):
    _,c=setup;out,body=create(c);d=detail(c,out['enrollment_id']);cid=course(c,'fixed')
    body={**body,'request_id':str(uuid4()),'course_id':cid,'profile':None,'existing_learner_id':out['learner_id'],'learner_version':d['learner_version'],'term':term(2)}
    second=call(c,'create',body);assert second.status_code==200,second.text
    assert second.json()['learner_id']==out['learner_id']
    body['request_id']=str(uuid4());assert call(c,'create',body).status_code==409

def test_archive_restore_and_counts_even_when_writes_disabled(setup,monkeypatch):
    _,c=setup;out,body=create(c);eid=out['enrollment_id']
    def monthly():return c.post('/portal/api/admin/enrollments/search',json={'month':'2026-10','course_id':body['course_id']}).json()
    assert monthly()['summary']['confirmed_people']==1
    a={'request_id':str(uuid4()),'reason':'가상 중복 보관','enrollment_id':eid,'version':1,'archived':True}
    assert call(c,'archive',a).status_code==200
    monkeypatch.setenv('RICHON_MANUAL_ENABLED','false')
    assert monthly()['summary']['confirmed_people']==0
    d=detail(c,eid);assert d['archived'] and len(d['terms'])==1
    a.update(request_id=str(uuid4()),version=d['version'],archived=False)
    assert call(c,'archive',a).status_code==200
    assert monthly()['summary']['confirmed_people']==1

def test_pending_extension_does_not_change_confirmed_months(setup):
    _,c=setup;out,body=create(c);eid=out['enrollment_id']
    ext={'request_id':str(uuid4()),'reason':'가상 연장 신청','enrollment_id':eid,'version':1,'term':term(12,False)}
    assert call(c,'terms/add',ext).status_code==200
    def row():return c.post('/portal/api/admin/enrollments/search',json={'month':'2026-10','course_id':body['course_id']}).json()['items'][0]
    assert row()['confirmed_months']==3 and row()['end_month']=='2026-12'
    d=detail(c,eid);pending=d['terms'][1]
    ext.update(request_id=str(uuid4()),version=d['version'],term_id=pending['term_id'],term=term(1,True))
    assert call(c,'terms/edit',ext).status_code==200
    assert row()['confirmed_months']==4 and row()['end_month']=='2027-01'
    ext.update(request_id=str(uuid4()),version=detail(c,eid)['version'],term=term(3,True))
    assert call(c,'terms/edit',ext).status_code==409

def test_fixed_course_rejects_extension(setup):
    _,c=setup;out,body=create(c,course(c,'fixed'),2)
    r=call(c,'terms/add',{'request_id':str(uuid4()),'reason':'가상 연장','enrollment_id':out['enrollment_id'],'version':1,'term':term(2)})
    assert r.status_code==409

def test_bad_duration_rolls_back_all_rows(setup,registry_db):
    _,c=setup;cid=course(c)
    with registry_db() as db:before=db.execute('SELECT count(*) FROM richon.enrollment_learners').fetchone()
    assert call(c,'create',create_body(cid,2)).status_code==422
    with registry_db() as db:assert db.execute('SELECT count(*) FROM richon.enrollment_learners').fetchone()==before

def test_search_masks_contacts_and_literal_wildcards(setup):
    _,c=setup;out,body=create(c)
    r=call(c,'search',{'q':body['profile']['name']});assert r.status_code==200,r.text
    assert len(r.json()['items'])==1 and 'manual@example.invalid' not in r.text
    assert r.json()['items'][0]['phone_masked']=='010-****-0000'
    for q in ["%' OR TRUE; --",'%','_\\']:
        assert call(c,'search',{'q':q}).json()['items']==[]

def test_commit_failure_never_returns_success_and_rolls_back(setup,registry_db):
    _,c=setup;cid=course(c)
    with registry_db() as db:
        before=db.execute('SELECT count(*) FROM richon.manual_enrollments').fetchone()
        db.execute("CREATE FUNCTION richon.manual_reject_commit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic commit error'; END; $$")
        db.execute('CREATE CONSTRAINT TRIGGER manual_reject_commit AFTER INSERT ON richon.manual_enrollments DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION richon.manual_reject_commit()')
    try:
        r=call(c,'create',create_body(cid));assert r.status_code in (409,503)
        with registry_db() as db:assert db.execute('SELECT count(*) FROM richon.manual_enrollments').fetchone()==before
    finally:
        with registry_db() as db:
            db.execute('DROP TRIGGER manual_reject_commit ON richon.manual_enrollments');db.execute('DROP FUNCTION richon.manual_reject_commit()')

def test_current_database_role_rechecked_before_write(setup,registry_db):
    actor,c=setup;body=model.Create(**create_body(course(c)))
    with registry_db() as db:db.execute("UPDATE richon.members SET role='member' WHERE member_id=%s",(actor,))
    with pytest.raises(manual_store.Rejected) as exc:manual_store.mutate(actor,'create',body)
    assert exc.value.status==403
