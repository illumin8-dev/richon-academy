"""Explicit return-path migration. Never called by the running portal or deploy."""
import argparse
import hashlib
from pathlib import Path
import db
from migration_runner import apply_standard_migration

VERSION = '008_login_return_paths'
DIRECTORY = Path(__file__).parent / 'migrations'
DEPENDENCIES = ('001_pending_orders', '002_auth_foundation', '007_oauth_handoff')


def apply_migration(*, connection_url=None):
    def checksum(name):
        return hashlib.sha256((DIRECTORY / (name + '.sql')).read_bytes()).hexdigest()

    return apply_standard_migration(
        db_module=db,
        directory=DIRECTORY,
        version=VERSION,
        dependencies=DEPENDENCIES,
        checksum=checksum,
        connection_url=connection_url,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Apply reviewed login return paths to a privately verified target.')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        parser.print_help()
        raise SystemExit(2)
    try:
        changed = apply_migration()
    except Exception:
        print('FAIL: login return migration not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: login return paths applied.' if changed else 'PASS: login return paths already applied.')
