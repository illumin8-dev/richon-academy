"""Explicit migration, with all dependency checksums verified before applying."""
import argparse
import hashlib
from pathlib import Path
import db
from migration_runner import apply_standard_migration

VERSION = '005_manual_registry'
DIRECTORY = Path(__file__).parent / 'migrations'
DEPENDENCIES = ('001_pending_orders','002_auth_foundation','003_portal_read_models','004_monthly_enrollments')

def apply_migration():
    checksum=lambda name: hashlib.sha256((DIRECTORY / (name + '.sql')).read_bytes()).hexdigest()
    return apply_standard_migration(
        db_module=db,
        directory=DIRECTORY,
        version=VERSION,
        dependencies=DEPENDENCIES,
        checksum=checksum,
    )

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed manual registry schema to a privately verified target.')
    parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply: parser.print_help();raise SystemExit(2)
    try: changed=apply_migration()
    except Exception:
        print('FAIL: manual migration not confirmed; no secrets printed.');raise SystemExit(1)
    print('PASS: manual schema created.' if changed else 'PASS: manual schema already applied.')
