"""Offline API, repository and migration tests. SQL execution is mocked here."""

import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import db
import main
import migrate_orders
import orders

URL = "postgresql://test_user:dummy_password@db.invalid/testdb?sslmode=require"
KEY = UUID("8e6861db-cdb3-4b64-975f-59cb1574b664")
BODY = {
    "course_id": "example-course-01",
    "customer_name": "테스트 신청자",
    "customer_phone": "01000000000",
    "customer_email": "student@example.invalid",
}


@pytest.fixture(autouse=True)
def no_live_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture
def client():
    with TestClient(main.app) as instance:
        yield instance


def order_row(request=None, amount=1000):
    request = request or orders.OrderRequest(**BODY)
    return (
        "ord_" + "a" * 32, request.course_id, "테스트 전용 강의", "test-only",
        amount, "KRW", "pending_payment", datetime(2026, 9, 22, tzinfo=timezone.utc),
        request.fingerprint(),
    )


def fake_database(monkeypatch, rows):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchone.side_effect = rows
    connection.cursor.return_value = cursor
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(db, "_connect", MagicMock(return_value=connection))
    return connection, cursor


def post(client, body=None, key=str(KEY)):
    return client.post("/orders", json=body if body is not None else BODY, headers={"Idempotency-Key": key})


def test_new_order_commits_before_201_and_uses_server_price(client, monkeypatch):
    connection, cursor = fake_database(monkeypatch, [None, ("테스트 전용 강의", "test-only", 1000), order_row()])
    response = post(client)
    assert response.status_code == 201
    assert response.json()["amount_krw"] == 1000
    assert response.json()["status"] == "pending_payment"
    assert response.headers["cache-control"] == "no-store"
    assert not any(k.startswith("customer_") for k in response.json())
    connection.__exit__.assert_called_once_with(None, None, None)
    insertion = next(c for c in cursor.execute.call_args_list if c.args[0] == orders.INSERT_ORDER)
    assert insertion.args[1][6] == 1000
    assert insertion.args[1][0].startswith("ord_")
    assert len(insertion.args[1][0]) == 36
    assert BODY["customer_name"] not in insertion.args[0]
    assert BODY["customer_email"] not in insertion.args[0]
    assert "SET TRANSACTION ISOLATION LEVEL READ COMMITTED" == cursor.execute.call_args_list[0].args[0]


def test_replay_returns_original_price_without_rechecking_course(client, monkeypatch):
    _, cursor = fake_database(monkeypatch, [order_row(amount=180000)])
    response = post(client)
    assert response.status_code == 200
    assert response.json()["amount_krw"] == 180000
    assert orders.FIND_COURSE not in [c.args[0] for c in cursor.execute.call_args_list]
    assert orders.INSERT_ORDER not in [c.args[0] for c in cursor.execute.call_args_list]


def test_conflicting_retry_is_409_without_customer_echo(client, monkeypatch):
    connection, _ = fake_database(monkeypatch, [order_row()])
    response = post(client, {**BODY, "customer_email": "different@example.invalid"})
    assert response.status_code == 409
    assert response.json() == {"detail": "idempotency_conflict"}
    assert "@" not in response.text
    assert connection.__exit__.call_args.args[0] is orders.IdempotencyConflict


def test_insert_conflict_uses_fresh_select_snapshot(client, monkeypatch):
    _, cursor = fake_database(monkeypatch, [None, ("테스트 전용 강의", "test-only", 2000), None, order_row()])
    response = post(client)
    assert response.status_code == 200
    assert response.json()["amount_krw"] == 1000
    queries = [c.args[0] for c in cursor.execute.call_args_list]
    assert queries[-2:] == [orders.INSERT_ORDER, orders.FIND_ORDER]


def test_insert_conflict_with_different_body_is_409(client, monkeypatch):
    fake_database(monkeypatch, [None, ("테스트 전용 강의", None, 1000), None, order_row()])
    assert post(client, {**BODY, "customer_name": "다른 테스트 신청자"}).status_code == 409


def test_missing_conflict_row_returns_retryable_failure(client, monkeypatch):
    fake_database(monkeypatch, [None, ("테스트 전용 강의", None, 1000), None, None])
    assert post(client).status_code == 503


def test_missing_or_disabled_course_does_not_insert(client, monkeypatch):
    connection, cursor = fake_database(monkeypatch, [None, None])
    response = post(client)
    assert response.status_code == 404
    assert response.json() == {"detail": "course_unavailable"}
    assert orders.INSERT_ORDER not in [c.args[0] for c in cursor.execute.call_args_list]
    assert connection.__exit__.call_args.args[0] is orders.CourseUnavailable


@pytest.mark.parametrize("field,value", [
    ("amount_krw", 1), ("price", 1), ("status", "paid"), ("customer_id", "someone-else"),
    ("course_id", "x'; DROP TABLE orders;--"), ("course_id", ""),
    ("customer_name", "  "), ("customer_name", "a" * 81), ("customer_name", "x\nsecret"),
    ("customer_name", "name\u200b"), ("customer_name", 123),
    ("customer_phone", "010123"), ("customer_phone", 1012345678),
    ("customer_phone", "+12125550000"), ("customer_phone", "010123456789"),
    ("customer_email", "not-email"), ("customer_email", "x@localhost"),
    ("customer_email", "x@example..com"), ("customer_email", "x\r\n@example.com"),
    ("customer_email", ".x@example.com"), ("customer_email", "x..y@example.com"),
    ("customer_email", "name <x@example.com>"), ("customer_email", None),
])
def test_invalid_or_tampered_input_never_touches_db(client, monkeypatch, field, value):
    connect = MagicMock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(db, "_connect", connect)
    response = post(client, {**BODY, field: value})
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_request"}
    assert response.headers["cache-control"] == "no-store"
    connect.assert_not_called()


@pytest.mark.parametrize("field", list(BODY))
def test_missing_fields_fail(client, field):
    body = dict(BODY)
    del body[field]
    assert post(client, body).status_code == 422


@pytest.mark.parametrize("key", [None, "", "bad", str(UUID(int=0)), "a" * 400])
def test_required_uuid4_retry_key(client, key):
    headers = {} if key is None else {"Idempotency-Key": key}
    response = client.post("/orders", json=BODY, headers=headers)
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_request"}


@pytest.mark.parametrize("value", ["010-0000-0000", "+82 10 0000 0000", "(010) 0000-0000"])
def test_phone_normalization_preserves_retry_fingerprint(value):
    canonical = orders.OrderRequest(**BODY)
    variant = orders.OrderRequest(**{**BODY, "customer_phone": value})
    assert variant.customer_phone == canonical.customer_phone
    assert variant.fingerprint() == canonical.fingerprint()


def test_domain_and_whitespace_normalization():
    value = orders.OrderRequest(**{**BODY, "customer_name": " 테스트 신청자 ", "customer_email": " student@EXAMPLE.INVALID "})
    assert value.fingerprint() == orders.OrderRequest(**BODY).fingerprint()


def test_sensitive_model_repr_does_not_include_customer():
    value = orders.OrderRequest(**BODY)
    for field in ("customer_name", "customer_email", "customer_phone"):
        assert BODY[field] not in repr(value)


def test_bad_json_has_no_input_echo(client):
    response = client.post("/orders", content='{"customer_name":"secret', headers={"Content-Type":"application/json", "Idempotency-Key":str(KEY)})
    assert response.status_code == 422
    assert response.json() == {"detail":"invalid_request"}


@pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
def test_no_list_or_mutation_api(client, method):
    assert getattr(client, method)("/orders").status_code == 405
    assert client.get("/orders/ord_" + "a" * 32).status_code == 404


def test_no_cors_opening(client):
    response = client.options("/orders", headers={"Origin":"https://richonacademy.com", "Access-Control-Request-Method":"POST"})
    assert "access-control-allow-origin" not in response.headers


def test_missing_db_is_safe_503(client):
    assert post(client).json() == {"detail":"order_storage_unavailable"}


def test_driver_error_does_not_leak_customer_or_credentials(client, monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(db, "_connect", MagicMock(side_effect=RuntimeError(URL + repr(BODY))))
    response = post(client)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    for value in [URL, "dummy_password", BODY["customer_name"], BODY["customer_email"], BODY["customer_phone"]]:
        assert value not in response.text
        assert value not in caplog.text


def test_commit_failure_never_returns_success(client, monkeypatch):
    connection, _ = fake_database(monkeypatch, [None, ("테스트 전용 강의", None, 1000), order_row()])
    connection.__exit__.side_effect = RuntimeError("commit failed")
    assert post(client).status_code == 503


def test_migration_executes_inside_connection_transaction(monkeypatch):
    connection, cursor = fake_database(monkeypatch, [(False, False), None])
    assert migrate_orders.apply_migration() is True
    connection.__exit__.assert_called_once_with(None, None, None)
    commands = [c.args[0] for c in cursor.execute.call_args_list]
    assert "SELECT pg_advisory_xact_lock(726426, 1)" in commands
    assert migrate_orders.MIGRATION.read_text() in commands
    assert "DROP TABLE" not in migrate_orders.MIGRATION.read_text().upper()
    assert "INSERT INTO richon.courses" not in migrate_orders.MIGRATION.read_text()


def test_migration_reentry_skips_applied_sql(monkeypatch):
    checksum = hashlib.sha256(migrate_orders.MIGRATION.read_bytes()).hexdigest()
    _, cursor = fake_database(monkeypatch, [(True, True), (checksum,)])
    assert migrate_orders.apply_migration() is False
    assert migrate_orders.MIGRATION.read_text() not in [c.args[0] for c in cursor.execute.call_args_list]


def test_migration_checksum_mismatch_rolls_back(monkeypatch):
    connection, _ = fake_database(monkeypatch, [(True, True), ("0" * 64,)])
    with pytest.raises(RuntimeError, match="checksum"):
        migrate_orders.apply_migration()
    assert connection.__exit__.call_args.args[0] is RuntimeError


def test_migration_requires_explicit_apply_flag(monkeypatch, capsys):
    import sys
    connect = MagicMock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(db, "_connect", connect)
    monkeypatch.setattr(sys, "argv", ["migrate_orders.py"])
    assert migrate_orders.main() == 2
    connect.assert_not_called()


def test_migration_cli_failure_hides_secret(monkeypatch, capsys):
    import sys
    monkeypatch.setattr(sys, "argv", ["migrate_orders.py", "--apply"])
    monkeypatch.setattr(migrate_orders, "apply_migration", MagicMock(side_effect=RuntimeError(URL)))
    assert migrate_orders.main() == 1
    captured = capsys.readouterr()
    assert URL not in captured.out + captured.err


def test_migration_refuses_unrelated_existing_namespace(monkeypatch):
    connection, cursor = fake_database(monkeypatch, [(True, False)])
    with pytest.raises(RuntimeError, match="namespace_exists"):
        migrate_orders.apply_migration()
    queries = [c.args[0] for c in cursor.execute.call_args_list]
    assert not any("CREATE SCHEMA" in q or "REVOKE" in q for q in queries)
    assert connection.__exit__.call_args.args[0] is RuntimeError
