"""Archive regression checks in disposable loopback PostgreSQL only; never Neon."""
import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

import auth_http as auth
import manual_portal
import monthly_portal
import portal
from main import invalid_request
# Import the complete fixture dependency chain into this test module.
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres, ORIGIN
from test_monthly_postgres import monthly_db
from test_manual_postgres import registry_db, setup, call, course, create, detail, term

pytestmark = pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB') != 'YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires disposable loopback richon_ci',
)


def monthly(client, **filters):
    response = client.post('/portal/api/admin/enrollments/search',
                           json={'month': '2026-10', **filters})
    assert response.status_code == 200, response.text
    return response.json()


def set_archived(client, enrollment_id, version, archived):
    response = call(client, 'archive', {
        'request_id': str(uuid4()), 'reason': 'synthetic archive regression',
        'enrollment_id': enrollment_id, 'version': version, 'archived': archived,
    })
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('confirmed', [True, False])
def test_archive_excluded_from_all_summary_fields_and_rows_then_restored(setup, confirmed):
    _, client = setup
    record, body = create(client, confirmed=confirmed)
    eid, cid = record['enrollment_id'], body['course_id']
    before = monthly(client, course_id=cid)
    assert before['summary']['total'] == 1
    assert before['summary']['confirmed_people'] == int(confirmed)
    assert before['summary']['pending_people'] == int(not confirmed)
    archived = set_archived(client, eid, 1, True)

    for scope in ('month', 'all'):
        for month in ('2026-10', '2026-12'):
            result = monthly(client, course_id=cid, scope=scope, month=month)
            assert all(value == 0 for value in result['summary'].values())
            assert result['items'] == [] and result['courses'] == []
            assert result['has_more'] is False

    # Archiving excludes the registration, but does not destroy its history.
    saved = detail(client, eid)
    assert saved['archived'] and len(saved['terms']) == 1
    assert saved['terms'][0]['grant_state'] == ('confirmed' if confirmed else 'pending')
    history = client.get('/portal/api/admin/enrollments/' + eid + '/terms')
    assert history.status_code == 200 and len(history.json()['items']) == 1

    set_archived(client, eid, archived['version'], False)
    restored = monthly(client, course_id=cid)
    assert restored == before


def test_archive_is_per_course_not_per_person(setup):
    _, client = setup
    first, body = create(client)
    saved = detail(client, first['enrollment_id'])
    second_course = course(client, 'fixed')
    response = call(client, 'create', {
        'request_id': str(uuid4()), 'reason': 'synthetic second course',
        'course_id': second_course, 'existing_learner_id': first['learner_id'],
        'learner_version': saved['learner_version'], 'term': term(2),
    })
    assert response.status_code == 200, response.text
    second = response.json()
    filters = {'q': body['profile']['name']}
    before = monthly(client, **filters)
    assert before['summary']['confirmed_people'] == 1
    assert before['summary']['confirmed_enrollments'] == 2

    archived = set_archived(client, first['enrollment_id'], 1, True)
    remaining = monthly(client, **filters)
    assert remaining['summary']['confirmed_people'] == 1
    assert remaining['summary']['confirmed_enrollments'] == 1
    assert [row['enrollment_id'] for row in remaining['items']] == [second['enrollment_id']]
    assert [row['course_id'] for row in remaining['courses']] == [second_course]

    set_archived(client, first['enrollment_id'], archived['version'], False)
    assert monthly(client, **filters) == before


def test_archive_exclusion_precedes_pagination_and_keeps_full_totals(setup):
    _, client = setup
    cid = course(client)
    records = [create(client, cid)[0] for _ in range(3)]
    archived_id = records[1]['enrollment_id']
    set_archived(client, archived_id, 1, True)
    expected_ids = {records[0]['enrollment_id'], records[2]['enrollment_id']}
    seen = set()
    for offset in (0, 1):
        result = monthly(client, course_id=cid, limit=1, offset=offset)
        assert result['summary']['total'] == 2
        assert result['summary']['confirmed_people'] == 2
        assert result['courses'][0]['confirmed_people'] == 2
        assert result['has_more'] is (offset == 0)
        assert len(result['items']) == 1
        seen.add(result['items'][0]['enrollment_id'])
    assert seen == expected_ids
    assert archived_id not in seen
    beyond = monthly(client, course_id=cid, limit=1, offset=2)
    assert beyond['items'] == [] and beyond['summary']['total'] == 2
    assert beyond['has_more'] is False


def test_archives_still_excluded_after_restart_without_manual_routes(setup, monkeypatch):
    _, client = setup
    record, body = create(client)
    set_archived(client, record['enrollment_id'], 1, True)
    monkeypatch.setenv('RICHON_MANUAL_ENABLED', 'false')

    app = FastAPI()
    app.add_exception_handler(RequestValidationError, invalid_request)
    assert auth.install_if_enabled(app)
    assert portal.install_if_enabled(app)
    assert monthly_portal.install_if_enabled(app)
    assert manual_portal.install_if_enabled(app) is False
    with TestClient(app, base_url=ORIGIN, headers=dict(client.headers)) as readonly:
        assert call(readonly, 'search', {}).status_code == 404
        result = monthly(readonly, course_id=body['course_id'])
        assert result['summary']['total'] == 0
        assert result['summary']['confirmed_people'] == 0
        assert result['courses'] == [] and result['items'] == []


def test_missing_applied_archive_table_returns_error_not_unfiltered_records(
        setup, registry_db, monkeypatch):
    _, client = setup
    record, body = create(client)
    set_archived(client, record['enrollment_id'], 1, True)
    monkeypatch.setenv('RICHON_MANUAL_ENABLED', 'false')
    # Fixture guard restricts this schema fault injection to local richon_ci.
    with registry_db() as connection:
        connection.execute('ALTER TABLE richon.manual_enrollments RENAME TO manual_archive_test_hidden')
    try:
        response = client.post('/portal/api/admin/enrollments/search',
                               json={'month': '2026-10', 'course_id': body['course_id']})
        assert response.status_code == 503
        assert response.json() == {'detail': 'monthly_store_unavailable'}
        assert response.headers['cache-control'] == 'no-store'
    finally:
        with registry_db() as connection:
            connection.execute('ALTER TABLE richon.manual_archive_test_hidden RENAME TO manual_enrollments')
    assert monthly(client, course_id=body['course_id'])['summary']['total'] == 0
