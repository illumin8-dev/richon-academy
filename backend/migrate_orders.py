"""Explicit schema setup, never called by an HTTP route or process startup."""

import argparse
import hashlib
from pathlib import Path

import db

MIGRATION = Path(__file__).parent / "migrations" / "001_pending_orders.sql"
VERSION = "001_pending_orders"


def apply_migration() -> bool:
    sql = MIGRATION.read_text(encoding="utf-8")
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    # Connection context commits all changes or rolls back every DDL statement.
    with db._connect(db.database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '15s'")
            cursor.execute("SET LOCAL lock_timeout = '10s'")
            cursor.execute("SELECT pg_advisory_xact_lock(726426, 1)")
            cursor.execute("SELECT to_regnamespace('richon') IS NOT NULL, to_regclass('richon.schema_migrations') IS NOT NULL")
            namespace_exists, ledger_exists = cursor.fetchone()
            if namespace_exists and not ledger_exists:
                # Do not adopt or change permissions on an unrelated namespace.
                raise RuntimeError("migration_namespace_exists")
            if not namespace_exists:
                cursor.execute("CREATE SCHEMA richon")
                cursor.execute("REVOKE ALL ON SCHEMA richon FROM PUBLIC")
                cursor.execute("""
                    CREATE TABLE richon.schema_migrations (
                        version text PRIMARY KEY, checksum char(64) NOT NULL,
                        applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("REVOKE ALL ON richon.schema_migrations FROM PUBLIC")
            cursor.execute("SELECT checksum FROM richon.schema_migrations WHERE version = %s", (VERSION,))
            existing = cursor.fetchone()
            if existing:
                if existing[0] != checksum:
                    raise RuntimeError("migration_checksum_mismatch")
                applied = False
            else:
                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO richon.schema_migrations (version, checksum) VALUES (%s, %s)",
                    (VERSION, checksum),
                )
                applied = True
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Create pending-order tables in the DATABASE_URL target.")
    parser.add_argument("--apply", action="store_true", help="Explicitly allow schema changes; no course/customer seed.")
    args = parser.parse_args()
    if not args.apply:
        parser.print_help()
        return 2
    try:
        applied = apply_migration()
    except Exception:
        # Exceptions may include database addresses, passwords or SQL values.
        print("FAIL: migration not confirmed. Check target/permissions privately; do not paste secrets.")
        return 1
    print("PASS: order tables created; no course/customer data added." if applied else "PASS: migration already applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
