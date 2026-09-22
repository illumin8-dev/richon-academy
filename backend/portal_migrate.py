"""Explicit staged migration for verified order ownership; never on startup."""
import argparse
import hashlib
from pathlib import Path
import db

VERSION = "003_portal_read_models"
DIRECTORY = Path(__file__).parent / "migrations"


def checksum(version):
    return hashlib.sha256((DIRECTORY / (version + ".sql")).read_bytes()).hexdigest()


def apply_migration() -> bool:
    with db._connect(db.database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '15s'")
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute("SELECT pg_advisory_xact_lock(726426, 1)")
            for predecessor in ("001_pending_orders", "002_auth_foundation"):
                cur.execute("SELECT checksum FROM richon.schema_migrations WHERE version=%s", (predecessor,))
                if cur.fetchone() != (checksum(predecessor),):
                    raise ValueError("portal_predecessor_mismatch")
            cur.execute("SELECT checksum FROM richon.schema_migrations WHERE version=%s", (VERSION,))
            existing = cur.fetchone()
            if existing:
                if existing != (checksum(VERSION),):
                    raise ValueError("portal_migration_mismatch")
                return False
            cur.execute((DIRECTORY / (VERSION + ".sql")).read_text(encoding="utf-8"))
            cur.execute("INSERT INTO richon.schema_migrations (version,checksum) VALUES (%s,%s)", (VERSION, checksum(VERSION)))
    return True


def main():
    parser = argparse.ArgumentParser(description="Apply staged portal ownership schema after target review.")
    parser.add_argument("--apply", action="store_true")
    if not parser.parse_args().apply:
        parser.print_help()
        return 2
    try:
        changed = apply_migration()
    except Exception:
        print("FAIL: portal migration not confirmed; no secrets printed.")
        return 1
    print("PASS: portal schema created." if changed else "PASS: portal schema already applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
