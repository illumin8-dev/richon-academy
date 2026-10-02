"""Explicit DB020 legacy-roster ledger migration. Never runs at application startup."""
import argparse
import hashlib
from pathlib import Path

import db
from migration_runner import apply_standard_migration

VERSION='020_legacy_roster_import'
DIRECTORY=Path(__file__).parent/'migrations'
DEPENDENCIES=('019_calendar_freeform',)


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
        advisory_slot=6,
    )


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed legacy-roster import ledger.')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        parser.print_help()
        raise SystemExit(2)
    try:
        changed=apply_migration()
    except Exception:
        print('FAIL: DB020 legacy roster migration not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: DB020 legacy roster ledger applied.' if changed else
          'PASS: DB020 legacy roster ledger already applied.')
