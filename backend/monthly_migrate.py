"""Explicit, transactional preparation only. Never invoked by the application."""
import argparse
import hashlib
from pathlib import Path
import db

VERSION = '004_monthly_enrollments'
DIRECTORY = Path(__file__).parent / 'migrations'


def apply_migration() -> bool:
    sql = (DIRECTORY / (VERSION + '.sql')).read_text(encoding='utf-8')
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    with db._connect(db.database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='15s'")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute('SELECT pg_advisory_xact_lock(726426,1)')
            for version in ('001_pending_orders','002_auth_foundation','003_portal_read_models'):
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s', (version,))
                expected = hashlib.sha256((DIRECTORY / (version + '.sql')).read_bytes()).hexdigest()
                if cur.fetchone() != (expected,):
                    raise ValueError('prior_migration_mismatch')
            cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s', (VERSION,))
            previous = cur.fetchone()
            if previous:
                if previous != (checksum,):
                    raise ValueError('monthly_migration_mismatch')
                return False
            cur.execute(sql)
            cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)', (VERSION,checksum))
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Explicit reviewed monthly schema setup; no seed data.')
    parser.add_argument('--apply', action='store_true')
    if not parser.parse_args().apply:
        parser.print_help()
        raise SystemExit(2)
    try:
        changed = apply_migration()
    except Exception:
        print('FAIL: monthly schema not confirmed; inspect privately without sharing secrets.')
        raise SystemExit(1) from None
    print('PASS: monthly schema created.' if changed else 'PASS: monthly schema already applied.')
