"""Full session + portal reads against disposable loopback PostgreSQL ONLY."""
import os
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
import pytest

import auth_core as core
import auth_http as http
import orders
import portal
import portal_store
import portal_migrate
from main import invalid_request
from test_orders_postgres import postgres
from test_auth_postgres import auth_postgres, guarded_target, CONSENT, ORIGIN

pytestmark = pytest.mark.skipif(
    os.getenv("RICHON_EMPTY_TEST_DB") != "YES" or not os.getenv("RICHON_TEST_DATABASE_URL"),
    reason="Requires the empty disposable loopback richon_ci database",
)


@pytest.fixture(scope="module")
def portal_postgres(auth_postgres):
    assert portal_migrate.apply_migration()
    return auth_postgres


@pytest.fixture
def example(portal_postgres, monkeypatch):
    run = uuid4().hex
    def member(role="member", provider="kakao"):
        identity = core.VerifiedIdentity(provider, "portal-ci", uuid4().hex, "가상동명이인-" + run)
        mid = core.register_verified_identity(identity, CONSENT)
        if role == "admin":
            with portal_postgres() as conn:
                conn.execute("UPDATE richon.members SET role='admin' WHERE member_id=%s", (mid,))
        return mid, core.issue_session(mid)
    a, sa = member()
    b, sb = member(provider="naver")
    admin, sx = member(role="admin")
    course = "portal-" + run
    with portal_postgres() as conn:
        conn.execute("INSERT INTO richon.courses (course_id,title,cohort,price_krw,enabled) VALUES (%s,%s,%s,1000,TRUE)",
                     (course,"가상 강의-"+run,"테스트 기수"))
    body = orders.OrderRequest(course_id=course,customer_name="가상동명이인-"+run,customer_phone="01000000000",customer_email="portal-test@example.invalid")
    ids = [orders.create_pending_order(body, uuid4()).order.order_id for _ in range(3)]
    with portal_postgres() as conn:
        conn.execute("INSERT INTO richon.member_order_links (order_id,member_id) VALUES (%s,%s),(%s,%s)", (ids[0],a,ids[1],b))
    app=FastAPI()
    app.add_exception_handler(RequestValidationError,invalid_request)
    app.include_router(http.make_router(http.AuthSettings(frozenset({ORIGIN}))))
    monkeypatch.setenv("RICHON_AUTH_ENABLED","true")
    monkeypatch.setenv("RICHON_PORTAL_ENABLED","true")
    portal.install_if_enabled(app)
    def client(token):
        return TestClient(app, base_url=ORIGIN,headers={"Cookie":f"{http.COOKIE}={token}"})
    return dict(a=a,b=b,sa=sa,sb=sb,sx=sx,admin=admin,ids=ids,run=run,course=course,client=client,app=app)


def test_migration_reentry_preserves_existing_orders(portal_postgres):
    with portal_postgres() as conn:
        before=conn.execute("SELECT count(*) FROM richon.orders").fetchone()
    assert portal_migrate.apply_migration() is False
    with portal_postgres() as conn:
        assert conn.execute("SELECT count(*) FROM richon.orders").fetchone()==before


def test_profile_and_ownership_do_not_match_names_or_contacts(example):
    e=example
    for key,owned,provider in [("sa",e['ids'][0],"kakao"),("sb",e['ids'][1],"naver")]:
        with e['client'](e[key].token) as client:
            profile=client.get('/portal/api/me').json()
            assert profile['providers']==[provider] and profile['linked_order_count']==1
            response=client.get('/portal/api/me/orders')
            assert response.status_code==200
            rows=response.json()['items']
            assert [r['order_id'] for r in rows]==[owned]
            assert rows[0]['amount_krw']==1000 and rows[0]['status']=='pending_payment'
            for private in ['customer_name','customer_phone','customer_email','request_fingerprint','idempotency_key','token_hash','subject','app_id']:
                assert private not in response.text
            assert e['ids'][2] not in response.text


def test_admin_lists_mask_contacts_and_do_not_expose_provider_subjects(example):
    e=example
    with e['client'](e['sx'].token) as client:
        response=client.get('/portal/api/admin/orders',params={'q':'가상동명이인-'+e['run']})
        assert response.status_code==200
        rows=response.json()['items']
        assert len(rows)==3 and sum(r['member_linked'] for r in rows)==2
        assert all(r['phone_masked']=='010-****-0000' for r in rows)
        assert all(r['email_masked']=='p***@example.invalid' for r in rows)
        assert '01000000000' not in response.text and 'portal-test@example.invalid' not in response.text
        members=client.get('/portal/api/admin/members',params={'q':e['run']})
        assert members.status_code==200 and len(members.json()['items'])==3
        assert all(x not in members.text for x in ['subject','app_id','token_hash','auth_version'])
        courses=client.get('/portal/api/admin/courses',params={'q':e['course']})
        assert courses.status_code==200 and len(courses.json()['items'])==1
        assert courses.json()['items'][0]['price_krw']==1000
        summary=client.get('/portal/api/admin/summary').json()
        assert summary['orders_total']>=3 and summary['unlinked_orders']>=1
        assert 'revenue' not in summary and 'enrollments' not in summary


@pytest.mark.parametrize('endpoint',['summary','members','courses','orders'])
def test_real_session_member_denied_admin(example,endpoint):
    with example['client'](example['sa'].token) as client:
        assert client.get('/portal/api/admin/'+endpoint).status_code==403


def test_pagination_and_filters(example):
    e=example
    with e['client'](e['sx'].token) as client:
        seen=[]
        for offset in range(3):
            response=client.get('/portal/api/admin/orders',params={'q':'가상동명이인-'+e['run'],'limit':1,'offset':offset})
            data=response.json();seen.append(data['items'][0]['order_id'])
            assert data['has_more'] is (offset<2)
        assert len(set(seen))==3
        filtered=client.get('/portal/api/admin/orders',params={'q':'가상동명이인-'+e['run'],'linked':'false'}).json()['items']
        assert [r['order_id'] for r in filtered]==[e['ids'][2]]
        assert client.get('/portal/api/admin/members',params={'q':e['run'],'status':'disabled'}).json()['items']==[]
        assert client.get('/portal/api/admin/courses',params={'q':e['course'],'enabled':'false'}).json()['items']==[]


@pytest.mark.parametrize('search',["%' OR TRUE; --",'%','_','\\'])
def test_search_is_literal_bound_sql(example,search):
    with example['client'](example['sx'].token) as client:
        for section in ['orders','members','courses']:
            response=client.get('/portal/api/admin/'+section,params={'q':search})
            assert response.status_code==200 and response.json()['items']==[]


def test_disabled_and_logged_out_sessions_cannot_read(example,portal_postgres):
    e=example
    with portal_postgres() as conn:
        conn.execute("UPDATE richon.members SET status='disabled' WHERE member_id=%s",(e['a'],))
    with e['client'](e['sa'].token) as client:
        assert client.get('/portal/api/me').status_code==401
    core.revoke_session(e['sb'].token)
    with e['client'](e['sb'].token) as client:
        assert client.get('/portal/api/me/orders').status_code==401


def test_admin_role_removal_takes_effect(example,portal_postgres):
    e=example
    with portal_postgres() as conn:
        conn.execute("UPDATE richon.members SET role='member' WHERE member_id=%s",(e['admin'],))
    with e['client'](e['sx'].token) as client:
        assert client.get('/portal/api/admin/orders').status_code==401


def test_order_cannot_be_linked_to_two_members(example,portal_postgres):
    import psycopg
    e=example
    with pytest.raises(psycopg.errors.UniqueViolation):
        with portal_postgres() as conn:
            conn.execute("INSERT INTO richon.member_order_links (order_id,member_id) VALUES (%s,%s)",(e['ids'][0],e['b']))
    with e['client'](e['sb'].token) as client:
        assert e['ids'][0] not in client.get('/portal/api/me/orders').text


def test_domain_read_transaction_rejects_writes(portal_postgres):
    import psycopg
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with portal_store.read_cursor() as cur:
            cur.execute('SHOW transaction_read_only');assert cur.fetchone()==('on',)
            cur.execute('DELETE FROM richon.member_order_links WHERE FALSE')


def test_reads_preserve_domain_rows(example,portal_postgres):
    sql="SELECT (SELECT count(*) FROM richon.members),(SELECT count(*) FROM richon.orders),(SELECT count(*) FROM richon.courses),(SELECT count(*) FROM richon.member_order_links)"
    with portal_postgres() as conn: before=conn.execute(sql).fetchone()
    with example['client'](example['sx'].token) as client:
        for route in ['me','me/orders','admin/summary','admin/members','admin/courses','admin/orders']:
            assert client.get('/portal/api/'+route).status_code==200
    with portal_postgres() as conn: assert conn.execute(sql).fetchone()==before


@pytest.mark.parametrize('verb',['post','patch','delete'])
def test_no_new_write_or_account_claim_routes(example,verb):
    with example['client'](example['sx'].token) as client:
        for route in ['admin/members','admin/courses','admin/orders','me/orders']:
            assert getattr(client,verb)('/portal/api/'+route).status_code==405
        assert client.get('/portal/api/me/orders/'+example['ids'][1]).status_code==404


def test_missing_read_schema_returns_unavailable_not_empty(example,portal_postgres):
    with portal_postgres() as conn:
        conn.execute('ALTER TABLE richon.member_order_links RENAME TO portal_test_hidden_links')
    try:
        with example['client'](example['sa'].token) as client:
            response=client.get('/portal/api/me/orders')
            assert response.status_code==503 and response.json()=={'detail':'portal_store_unavailable'}
    finally:
        with portal_postgres() as conn:
            conn.execute('ALTER TABLE richon.portal_test_hidden_links RENAME TO member_order_links')
