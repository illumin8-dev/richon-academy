"""Explicit migration, with all dependency checksums verified before applying."""
import argparse
import hashlib
from pathlib import Path
import db

VERSION = '006_pricing_notes'
DIRECTORY = Path(__file__).parent / 'migrations'
DEPENDENCIES = ('001_pending_orders','002_auth_foundation','003_portal_read_models','004_monthly_enrollments','005_manual_registry')

def apply_migration():
    checksum = lambda name: hashlib.sha256((DIRECTORY / (name + '.sql')).read_bytes()).hexdigest()
    with db._connect(db.database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='15s'")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute('SELECT pg_advisory_xact_lock(726426,1)')
            for version in DEPENDENCIES:
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
                if cur.fetchone() != (checksum(version),): raise ValueError('dependency_mismatch')
            cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(VERSION,))
            old = cur.fetchone()
            if old:
                if old != (checksum(VERSION),): raise ValueError('migration_mismatch')
                return False
            cur.execute((DIRECTORY / (VERSION+'.sql')).read_text())
            cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',(VERSION,checksum(VERSION)))
    return True

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed manual registry schema to a privately verified target.')
    parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply: parser.print_help();raise SystemExit(2)
    try: changed=apply_migration()
    except Exception:
        print('FAIL: pricing/notes migration not confirmed; no secrets printed.');raise SystemExit(1)
    print('PASS: pricing/notes schema created.' if changed else 'PASS: pricing/notes schema already applied.')
