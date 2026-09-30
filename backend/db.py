"""Read-only connectivity probe. No schema or customer-data operations."""

import os
from contextlib import AbstractContextManager
from typing import Any
from urllib.parse import urlsplit


class DatabaseConfigurationError(Exception):
    """Safe exception: never include the connection string in the message."""


def database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value or any(char.isspace() for char in value):
        raise DatabaseConfigurationError("DATABASE_URL is missing or invalid")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"postgresql", "postgres"}
            and bool(parsed.hostname)
            and bool(parsed.username)
            and bool(parsed.password)
            and parsed.path not in {"", "/"}
            and not parsed.fragment
        )
        _ = parsed.port  # Reject malformed/out-of-range ports before connecting.
    except ValueError:
        raise DatabaseConfigurationError("DATABASE_URL is invalid") from None
    if not valid or value.startswith(("'", '"')) or value.endswith(("'", '"')):
        raise DatabaseConfigurationError("DATABASE_URL is invalid")
    return value


def _connect(url: str) -> AbstractContextManager[Any]:
    # Lazy import keeps the process-health check independent of the DB driver.
    # Deployment requirements install psycopg[binary]; no subprocess/psql usage.
    import psycopg

    return psycopg.connect(
        url,
        connect_timeout=10,
        prepare_threshold=None,
        sslmode="verify-full",
        sslrootcert="system",
    )


def check_database() -> bool:
    """Open one short connection, issue SELECT 1, and always close it.

    TLS verifies the server certificate using system CA certificates. The binary
    Psycopg distribution bundles a modern libpq supporting sslrootcert=system.
    SET LOCAL is transaction-scoped and works with a transaction-pooler endpoint.
    """
    url = database_url()
    with _connect(url) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
