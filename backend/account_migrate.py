"""Explicit account-lifecycle migration. Never run on app startup or deploy."""
import argparse
import hashlib
from pathlib import Path
import db
from migration_runner import apply_standard_migration

VERSION = '010_account_lifecycle'
DIRECTORY = Path(__file__).parent / 'migrations'
DEPENDENCIES = ('001_pending_orders','002_auth_foundation','003_portal_read_models',
                '007_oauth_handoff','008_login_return_paths','009_member_profiles')


def checksum(name):
    return hashlib.sha256((DIRECTORY / (name + '.sql')).read_bytes()).hexdigest()


def apply_migration(*, connection_url=None):
    return apply_standard_migration(
        db_module=db,
        directory=DIRECTORY,
        version=VERSION,
        dependencies=DEPENDENCIES,
        checksum=checksum,
        connection_url=connection_url,
        statement_timeout_seconds=20,
    )


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
