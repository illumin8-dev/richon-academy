"""Order HTTP/ASGI routes with real, disposable PostgreSQL transactions.

Runs only against the CI loopback richon_ci database. Never calls the deployed
Cloud Run service, Neon, a PG, email, or messaging APIs. Reuses the existing
explicit opt-in fixture; that fixture creates/removes only its test schema.
TestClient exercises the application route, not real browser/TLS/IAM transport.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import main
from test_orders_postgres import course, postgres  # Reuse guarded fixtures.

pytestmark = pytest.mark.skipif(
    os.getenv("RICHON_EMPTY_TEST_DB") != "YES" or not os.getenv("RICHON_TEST_DATABASE_URL"),
    reason="Requires the explicitly authorized CI-only disposable database",
)


@pytest.fixture(scope="module", autouse=True)
def require_loopback_ci_database():
    target = urlsplit(os.environ["RICHON_TEST_DATABASE_URL"])
    if (target.scheme not in {"postgres", "postgresql"}
            or target.hostname not in {"127.0.0.1", "localhost", "::1"}
            or target.path != "/richon_ci" or os.getenv("DATABASE_URL")):
        pytest.fail("Refusing a non-loopback CI database or configured application database")


@pytest.fixture
def api(postgres):
    with TestClient(main.app) as client:
        yield client


def submit(api, course, key, changes=None):
    body = course.model_dump()
    if changes:
        body.update(changes)
    return api.post("/orders", json=body, headers={"Idempotency-Key": str(key)})


def count_for_course(postgres, course):
    # A different connection must observe a committed result, not an uncommitted insert.
    with postgres() as connection:
        return connection.execute(
            "SELECT count(*) FROM richon.orders WHERE course_id=%s", (course.course_id,)
        ).fetchone()[0]


def assert_safe_error(response, status, detail):
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert response.headers["cache-control"] == "no-store"


def test_http_created_order_is_committed_and_uses_server_price(api, postgres, course):
    key = uuid4()
    response = submit(api, course, key)
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    order = response.json()
    assert set(order) == {
        "order_id", "course_id", "course_title", "cohort", "amount_krw",
        "currency", "status", "created_at",
    }
    assert order["amount_krw"] == 1000
    assert order["status"] == "pending_payment"
    assert order["currency"] == "KRW"
    assert course.customer_phone not in response.text
    assert course.customer_email not in response.text
    with postgres() as connection:
        stored = connection.execute(
            "SELECT order_id, amount_krw, status, customer_name, customer_phone, "
            "customer_email FROM richon.orders WHERE idempotency_key=%s", (str(key),)
        ).fetchone()
    assert stored == (order["order_id"], 1000, "pending_payment", "테스트", "01000000000", "test@example.invalid")
    assert count_for_course(postgres, course) == 1


def test_http_normalized_retry_returns_same_order(api, postgres, course):
    key = uuid4()
    first = submit(api, course, key, {
        "customer_name": " 테스트 ", "customer_phone": "+82 10-0000-0000",
        "customer_email": "test@EXAMPLE.INVALID",
    })
    second = submit(api, course, key)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert count_for_course(postgres, course) == 1


@pytest.mark.parametrize("repeat", range(3))
def test_http_eight_simultaneous_retries_create_one_order(api, postgres, course, repeat):
    key = uuid4()
    barrier = Barrier(8)

    def run(_):
        barrier.wait(timeout=15)
        return submit(api, course, key)

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(run, range(8)))
    assert sorted(response.status_code for response in responses) == [200] * 7 + [201]
    assert len({response.json()["order_id"] for response in responses}) == 1
    assert count_for_course(postgres, course) == 1


def test_http_simultaneous_different_payload_same_key_conflicts(api, postgres, course):
    key = uuid4()
    barrier = Barrier(2)

    def run(changes):
        barrier.wait(timeout=15)
        return submit(api, course, key, changes)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(run, [None, {"customer_name": "다른 가상 신청자"}]))
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert_safe_error(next(r for r in responses if r.status_code == 409), 409, "idempotency_conflict")
    assert count_for_course(postgres, course) == 1


@pytest.mark.parametrize("forged", [
    {"amount": 1}, {"amount_krw": 1}, {"status": "paid"}, {"currency": "USD"},
    {"order_id": "ord_" + "a" * 32}, {"course_title": "forged"}, {"paid_at": "2026-01-01"},
])
def test_http_forged_fields_are_rejected_without_insert(api, postgres, course, forged):
    assert_safe_error(submit(api, course, uuid4(), forged), 422, "invalid_request")
    assert count_for_course(postgres, course) == 0


@pytest.mark.parametrize("field", ["course_id", "customer_name", "customer_phone", "customer_email"])
def test_http_missing_fields_are_rejected_without_insert(api, postgres, course, field):
    body = course.model_dump()
    del body[field]
    response = api.post("/orders", json=body, headers={"Idempotency-Key": str(uuid4())})
    assert_safe_error(response, 422, "invalid_request")
    assert count_for_course(postgres, course) == 0


def test_http_malformed_json_is_rejected_without_insert(api, postgres, course):
    response = api.post("/orders", content="{", headers={
        "Content-Type": "application/json", "Idempotency-Key": str(uuid4()),
    })
    assert_safe_error(response, 422, "invalid_request")
    assert count_for_course(postgres, course) == 0


@pytest.mark.parametrize("key", [None, "not-a-uuid", "00000000-0000-1000-8000-000000000000"])
def test_http_idempotency_key_is_required_and_v4(api, postgres, course, key):
    headers = {} if key is None else {"Idempotency-Key": key}
    response = api.post("/orders", json=course.model_dump(), headers=headers)
    assert_safe_error(response, 422, "invalid_request")
    assert count_for_course(postgres, course) == 0


@pytest.mark.parametrize("missing", [False, True])
def test_http_unavailable_course_creates_no_order(api, postgres, course, missing):
    changes = {"course_id": "missing-" + uuid4().hex} if missing else None
    if not missing:
        with postgres() as connection:
            connection.execute("UPDATE richon.courses SET enabled=FALSE WHERE course_id=%s", (course.course_id,))
    assert_safe_error(submit(api, course, uuid4(), changes), 404, "course_unavailable")
    assert count_for_course(postgres, course) == 0


def test_http_price_snapshot_survives_change_and_disable(api, postgres, course):
    key = uuid4()
    first = submit(api, course, key)
    assert first.status_code == 201
    with postgres() as connection:
        connection.execute(
            "UPDATE richon.courses SET price_krw=2000, title='Changed test title' WHERE course_id=%s",
            (course.course_id,),
        )
    retry = submit(api, course, key)
    assert retry.status_code == 200 and retry.json() == first.json()
    new_order = submit(api, course, uuid4())
    assert new_order.status_code == 201 and new_order.json()["amount_krw"] == 2000
    with postgres() as connection:
        connection.execute("UPDATE richon.courses SET enabled=FALSE WHERE course_id=%s", (course.course_id,))
    assert submit(api, course, key).json() == first.json()
    assert_safe_error(submit(api, course, uuid4()), 404, "course_unavailable")
    assert count_for_course(postgres, course) == 2


def test_http_new_client_can_retry_committed_order(postgres, course):
    key = uuid4()
    with TestClient(main.app) as first_client:
        first = submit(first_client, course, key)
    with TestClient(main.app) as second_client:
        second = submit(second_client, course, key)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json() == second.json()
    assert count_for_course(postgres, course) == 1


def test_http_order_list_and_detail_remain_unavailable(api, postgres, course):
    created = submit(api, course, uuid4())
    assert created.status_code == 201
    assert api.get("/orders").status_code == 405
    assert api.get("/orders/" + created.json()["order_id"]).status_code == 404
    assert count_for_course(postgres, course) == 1


def test_http_actual_commit_failure_returns_503_and_rolls_back(api, postgres, course):
    from psycopg import sql

    # A deferred trigger fails at COMMIT, after INSERT ... RETURNING succeeds.
    # The trigger/function exist only in this disposable fixture's own schema.
    with postgres() as connection:
        connection.execute("""
            CREATE FUNCTION richon.e2e_reject_order_commit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.course_id = TG_ARGV[0] THEN
                    RAISE EXCEPTION 'test-only deferred commit failure';
                END IF;
                RETURN NEW;
            END $$
        """)
        connection.execute(sql.SQL("""
            CREATE CONSTRAINT TRIGGER e2e_reject_order_commit AFTER INSERT ON richon.orders
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION richon.e2e_reject_order_commit({})
        """).format(sql.Literal(course.course_id)))
    try:
        assert_safe_error(submit(api, course, uuid4()), 503, "order_storage_unavailable")
        assert count_for_course(postgres, course) == 0
    finally:
        with postgres() as connection:
            connection.execute("DROP TRIGGER e2e_reject_order_commit ON richon.orders")
            connection.execute("DROP FUNCTION richon.e2e_reject_order_commit()")
