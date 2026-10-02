"""Explicit DB017 hardening migration. Never runs at application startup."""
import argparse
import hashlib
from pathlib import Path
import db
from migration_runner import apply_standard_migration

VERSION='017_monthly_runtime_hardening'
DIRECTORY=Path(__file__).parent/'migrations'
DEPENDENCIES=('004_monthly_enrollments','005_manual_registry')


def checksum(name):
    return hashlib.sha256((DIRECTORY/(name+'.sql')).read_bytes()).hexdigest()


def apply_migration(*, connection_url=None):
    return apply_standard_migration(
        db_module=db,
        directory=DIRECTORY,
        version=VERSION,
        dependencies=DEPENDENCIES,
        checksum=checksum,
        connection_url=connection_url,
        advisory_slot=5,
        dependency_error_with_version=True,
    )


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed monthly restricted-runtime hardening.')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        parser.print_help();raise SystemExit(2)
    try:
        changed=apply_migration()
    except Exception:
        print('FAIL: DB017 hardening not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: DB017 hardening applied.' if changed else 'PASS: DB017 hardening already applied.')
