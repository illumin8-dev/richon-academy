"""Explicit staged 004 migration. No startup/HTTP migration or real DB default."""
import argparse
import hashlib
from pathlib import Path
import db

VERSION = '004_enrollment_read_models'
DIRECTORY = Path(__file__).parent / 'migrations'


def checksum(version):
    return hashlib.sha256((DIRECTORY / (version + '.sql')).read_bytes()).hexdigest()


def apply_migration() -> bool:
    applied = False
    with db._connect(db.database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '15s'")
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute('SELECT pg_advisory_xact_lock(726426, 1)')
            for version in ('001_pending_orders','002_auth_foundation','003_portal_read_models'):
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s', (version,))
                if cur.fetchone() != (checksum(version),):
                    raise ValueError('enrollment_predecessor_mismatch')
            cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s', (VERSION,))
            existing = cur.fetchone()
            if existing:
                if existing != (checksum(VERSION),):
                    raise ValueError('enrollment_migration_mismatch')
            else:
                cur.execute((DIRECTORY / (VERSION + '.sql')).read_text(encoding='utf-8'))
                cur.execute('INSERT INTO richon.schema_migrations (version,checksum) VALUES (%s,%s)', (VERSION,checksum(VERSION)))
                applied = True
    return applied


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Apply reviewed enrollment schema to an explicitly checked target.')
    parser.add_argument('--apply', action='store_true')
    if not parser.parse_args().apply:
        parser.print_help()
        raise SystemExit(2)
    try:
        changed = apply_migration()
    except Exception:
        print('FAIL: enrollment migration not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: enrollment schema created.' if changed else 'PASS: enrollment schema already applied.')
