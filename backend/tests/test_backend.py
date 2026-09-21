"""Offline tests. Fake connections do NOT establish a real Neon connection."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import db
import main

# Reserved .invalid hostname and dummy credentials: no customer secrets.
URL = "postgresql://test_user:dummy_password@db.invalid/testdb?sslmode=require"


@pytest.fixture(autouse=True)
def no_real_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture
def client():
    with TestClient(main.app) as instance:
        yield instance


def test_health_does_not_connect(client, monkeypatch):
    connect = MagicMock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(db, "_connect", connect)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
    connect.assert_not_called()


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/admin"])
def test_unimplemented_routes_stay_closed(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/health", "/health/db"])
def test_no_write_methods(client, path):
    assert client.post(path).status_code == 405


def test_database_url_preserves_query_parameters(monkeypatch):
    url = URL + "&channel_binding=require"
    monkeypatch.setenv("DATABASE_URL", url)
    assert db.database_url() == url


@pytest.mark.parametrize("value", [
    "", "   ", "psql '" + URL + "'", "'" + URL + "'", '"' + URL + '"',
    "https://db.invalid", "postgresql:///testdb", "postgresql://user@db.invalid/testdb",
    "postgresql://user:pass@db.invalid/", "postgresql://user:pass@db.invalid:bad/testdb",
    "postgresql://user:pass@db.invalid:99999/testdb", URL + "\nextra", URL + "#fragment",
])
def test_bad_configuration_is_rejected_without_secret_echo(monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(db.DatabaseConfigurationError) as error:
        db.database_url()
    assert "dummy_password" not in str(error.value)
    assert "postgresql://" not in str(error.value)


def test_missing_configuration_returns_safe_503(client):
    response = client.get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"detail": "database_configuration_invalid"}
    assert response.headers["cache-control"] == "no-store"


def test_driver_arguments(monkeypatch):
    connect = MagicMock()
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    db._connect(URL)
    connect.assert_called_once_with(
        URL, connect_timeout=10, prepare_threshold=None,
        sslmode="verify-full", sslrootcert="system",
    )


def fake_connection(monkeypatch, row=(1,)):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.return_value = row
    connection.cursor.return_value = cursor
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(db, "_connect", MagicMock(return_value=connection))
    return connection, cursor


def test_database_probe_uses_read_only_transaction_and_closes(monkeypatch):
    connection, cursor = fake_connection(monkeypatch)
    assert db.check_database() is True
    assert connection.read_only is True
    assert [call.args[0] for call in cursor.execute.call_args_list] == [
        "SET LOCAL statement_timeout = '5s'", "SELECT 1",
    ]
    cursor.__exit__.assert_called_once()
    connection.__exit__.assert_called_once()


def test_database_probe_closes_on_query_failure(monkeypatch):
    connection, cursor = fake_connection(monkeypatch)
    cursor.execute.side_effect = RuntimeError("simulated failure")
    # Real context managers do not suppress exceptions.
    connection.__exit__.return_value = False
    cursor.__exit__.return_value = False
    with pytest.raises(RuntimeError):
        db.check_database()
    connection.__exit__.assert_called_once()


def test_reachable_database_response(client, monkeypatch):
    fake_connection(monkeypatch)
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}


def test_unexpected_query_result_is_not_success(client, monkeypatch):
    fake_connection(monkeypatch, row=None)
    assert client.get("/health/db").status_code == 503


def test_failure_never_leaks_secret(client, monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(db, "_connect", MagicMock(side_effect=RuntimeError(URL)))
    response = client.get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"detail": "database_unavailable"}
    for sensitive in ["dummy_password", "test_user", "db.invalid", URL]:
        assert sensitive not in response.text
        assert sensitive not in caplog.text
