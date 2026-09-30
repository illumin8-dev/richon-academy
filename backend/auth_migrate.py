"""Explicit second migration. No network calls on import, startup, or HTTP."""
import argparse
import hashlib
from pathlib import Path

import db

VERSION = "002_auth_foundation"
MIGRATION = Path(__file__).parent / "migrations" / (VERSION + ".sql")


def apply_migration() -> bool:
    sql = MIGRATION.read_text(encoding="utf-8")
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    with db._connect(db.database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '15s'")
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute("SELECT pg_advisory_xact_lock(726426, 1)")
            cur.execute("SELECT to_regclass('richon.schema_migrations') IS NOT NULL")
            if not cur.fetchone()[0]:
                raise ValueError("base_migration_required")
            cur.execute("SELECT checksum FROM richon.schema_migrations WHERE version=%s", ("001_pending_orders",))
            base = cur.fetchone()
            original = MIGRATION.with_name("001_pending_orders.sql").read_text(encoding="utf-8")
            if not base or base[0] != hashlib.sha256(original.encode()).hexdigest():
                raise ValueError("base_migration_mismatch")
            cur.execute("SELECT checksum FROM richon.schema_migrations WHERE version=%s", (VERSION,))
            existing = cur.fetchone()
            if existing:
                if existing[0] != checksum:
                    raise ValueError("auth_migration_mismatch")
                applied = False
            else:
                # Do not use IF NOT EXISTS to silently adopt unrelated tables.
                cur.execute(sql)
                cur.execute("INSERT INTO richon.schema_migrations (version,checksum) VALUES (%s,%s)", (VERSION, checksum))
                applied = True
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicit auth schema setup; verify the target privately first.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.print_help()
        return 2
    try:
        changed = apply_migration()
    except Exception:
        # No exception message/SQL/DSN/PII in logs.
        print("FAIL: auth migration not confirmed; no diagnostic secrets are printed.")
        return 1
    print("PASS: auth schema created." if changed else "PASS: auth schema already applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
