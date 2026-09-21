"""Opt-in SQL/concurrency tests against an EMPTY DISPOSABLE PostgreSQL database.

Never use the application's real DATABASE_URL here. The fixture refuses an
existing richon schema. It creates and finally removes ONLY its new richon schema.
Example environment: RICHON_EMPTY_TEST_DB=YES, RICHON_TEST_DATABASE_URL=<test-only DSN>.
No database credentials are included in this repository.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest

import db
import migrate_orders
import orders

pytestmark = pytest.mark.skipif(
    os.getenv("RICHON_EMPTY_TEST_DB") != "YES" or not os.getenv("RICHON_TEST_DATABASE_URL"),
    reason="Requires an explicitly authorized, empty disposable PostgreSQL database",
)


@pytest.fixture(scope="module")
def postgres():
    psycopg = pytest.importorskip("psycopg")
    url = os.environ["RICHON_TEST_DATABASE_URL"]
    if url == os.getenv("DATABASE_URL"):
        pytest.fail("Refusing the application's configured DATABASE_URL")

    def connect(_url=None):
        # The disposable test DB controls its own TLS settings. This adapter is
        # test-only and does not verify production TLS or Cloud Run IAM.
        return psycopg.connect(url, connect_timeout=10, prepare_threshold=None)

    with connect() as connection:
        if connection.execute("SELECT to_regnamespace('richon')").fetchone()[0] is not None:
            pytest.fail("Refusing a database with an existing richon schema")
    created = False
    with patch.object(db, "_connect", connect), patch.dict(os.environ, {"DATABASE_URL": url}):
        try:
            assert migrate_orders.apply_migration()
            created = True
            yield connect
        finally:
            if created:
                with connect() as connection:
                    connection.execute("DROP SCHEMA richon CASCADE")


@pytest.fixture
def course(postgres):
    course_id = "test-" + uuid4().hex
    with postgres() as connection:
        connection.execute(
            "INSERT INTO richon.courses (course_id, title, price_krw, enabled) VALUES (%s, %s, %s, TRUE)",
            (course_id, "Integration test only", 1000),
        )
    return orders.OrderRequest(course_id=course_id, customer_name="테스트", customer_phone="01000000000", customer_email="test@example.invalid")


def test_postgres_schema_reentry(postgres):
    assert migrate_orders.apply_migration() is False


def test_postgres_persistence_and_retry(postgres, course):
    key = uuid4()
    first = orders.create_pending_order(course, key)
    second = orders.create_pending_order(course, key)
    assert first.created is True and second.created is False
    assert first.order == second.order
    with postgres() as connection:
        row = connection.execute("SELECT amount_krw, status FROM richon.orders WHERE order_id=%s", (first.order.order_id,)).fetchone()
    assert row == (1000, "pending_payment")


def test_postgres_simultaneous_retry_creates_one_order(postgres, course):
    key = uuid4()
    barrier = Barrier(8)

    def run(_):
        barrier.wait(timeout=15)
        return orders.create_pending_order(course, key)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(run, range(8)))
    assert sum(result.created for result in results) == 1
    assert len({result.order.order_id for result in results}) == 1
    with postgres() as connection:
        assert connection.execute("SELECT count(*) FROM richon.orders WHERE idempotency_key=%s", (str(key),)).fetchone() == (1,)


def test_postgres_concurrent_key_conflict(postgres, course):
    key = uuid4()
    barrier = Barrier(2)
    different = orders.OrderRequest(**{**course.model_dump(), "customer_name": "다른 테스트"})

    def run(body):
        barrier.wait(timeout=15)
        try:
            return orders.create_pending_order(body, key)
        except orders.IdempotencyConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, [course, different]))
    assert results.count("conflict") == 1
    assert sum(isinstance(result, orders.OrderResult) and result.created for result in results) == 1


def test_postgres_price_snapshot_and_disabled_course(postgres, course):
    key = uuid4()
    first = orders.create_pending_order(course, key)
    with postgres() as connection:
        connection.execute("UPDATE richon.courses SET price_krw=2000, enabled=FALSE WHERE course_id=%s", (course.course_id,))
    assert orders.create_pending_order(course, key).order == first.order
    with pytest.raises(orders.CourseUnavailable):
        orders.create_pending_order(course, uuid4())
    with postgres() as connection:
        assert connection.execute("SELECT count(*) FROM richon.orders WHERE course_id=%s", (course.course_id,)).fetchone() == (1,)


def test_postgres_paid_state_cannot_be_forged(postgres, course):
    psycopg = pytest.importorskip("psycopg")
    result = orders.create_pending_order(course, uuid4())
    with pytest.raises(psycopg.errors.CheckViolation):
        with postgres() as connection:
            connection.execute("UPDATE richon.orders SET status='paid' WHERE order_id=%s", (result.order.order_id,))
    with postgres() as connection:
        assert connection.execute("SELECT status FROM richon.orders WHERE order_id=%s", (result.order.order_id,)).fetchone() == ("pending_payment",)
