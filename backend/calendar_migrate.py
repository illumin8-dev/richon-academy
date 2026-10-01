"""Explicit central-calendar migration. Never runs at application startup."""
import argparse
import hashlib
from pathlib import Path
import db

VERSION='018_calendar_events'
DIRECTORY=Path(__file__).parent/'migrations'
DEPENDENCIES=('016_course_entitlements',)

def checksum(name):
    return hashlib.sha256((DIRECTORY/(name+'.sql')).read_bytes()).hexdigest()

def apply_migration(*, connection_url=None):
    target=db.database_url() if connection_url is None else connection_url
    with db._connect(target) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='15s'")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute('SELECT pg_advisory_xact_lock(726426,4)')
            for version in DEPENDENCIES:
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(version,))
                if cur.fetchone()!=(checksum(version),):
                    raise ValueError('dependency_mismatch_'+version)
            cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(VERSION,))
            old=cur.fetchone()
            if old:
                if old!=(checksum(VERSION),): raise ValueError('migration_mismatch')
                return False
            cur.execute((DIRECTORY/(VERSION+'.sql')).read_text())
            cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                        (VERSION,checksum(VERSION)))
    return True

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed central-calendar schema.')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        parser.print_help(); raise SystemExit(2)
    try: changed=apply_migration()
    except Exception:
        print('FAIL: calendar migration not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: central calendar schema created.' if changed else
          'PASS: central calendar schema already applied.')
