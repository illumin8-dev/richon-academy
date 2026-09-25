"""Explicit account-lifecycle migration. Never run on app startup or deploy."""
import argparse
import hashlib
from pathlib import Path
import db

VERSION = '010_account_lifecycle'
DIRECTORY = Path(__file__).parent / 'migrations'
DEPENDENCIES = ('001_pending_orders','002_auth_foundation','003_portal_read_models',
                '007_oauth_handoff','008_login_return_paths','009_member_profiles')


def checksum(name):
    return hashlib.sha256((DIRECTORY / (name + '.sql')).read_bytes()).hexdigest()


def apply_migration(*, connection_url=None):
    target = db.database_url() if connection_url is None else connection_url
    with db._connect(target) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='20s'")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute('SELECT pg_advisory_xact_lock(726426,1)')
            for version in DEPENDENCIES:
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
                if cur.fetchone() != (checksum(version),):
                    raise ValueError('dependency_mismatch')
            cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(VERSION,))
            old = cur.fetchone()
            if old:
                if old != (checksum(VERSION),):
                    raise ValueError('migration_mismatch')
                return False
            cur.execute((DIRECTORY / (VERSION+'.sql')).read_text())
            cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                        (VERSION,checksum(VERSION)))
    return True


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed account-lifecycle schema to a privately verified target.')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        parser.print_help()
        raise SystemExit(2)
    try:
        changed=apply_migration()
    except Exception:
        print('FAIL: account lifecycle migration not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: account lifecycle schema applied.' if changed else 'PASS: account lifecycle schema already applied.')
