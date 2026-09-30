"""Owner-run expiry cleanup for account-lifecycle retained records.

Never imported by the portal runtime and never invoked at app startup. Production
CLI requires the known owner/database and an explicit --apply flag.
"""
import argparse
import hashlib
from pathlib import Path

import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import db

VERSION='010_account_lifecycle'
MIGRATION=ROOT/'backend/migrations'/(VERSION+'.sql')


def cleanup(*,connection_url=None,expected_database=None,expected_user=None):
    target=db.database_url() if connection_url is None else connection_url
    checksum=hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    with db._connect(target) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='20s'")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute('SELECT pg_advisory_xact_lock(726426,2)')
            if expected_database is not None or expected_user is not None:
                cur.execute('SELECT current_database(),current_user')
                database,user=cur.fetchone()
                if database!=expected_database or user!=expected_user:
                    raise ValueError('wrong_cleanup_target')
            cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(VERSION,))
            if cur.fetchone()!=(checksum,):
                raise ValueError('account_migration_mismatch')
            counts={}
            for table in ('provider_unlink_failures','oauth_account_attempts',
                          'oauth_link_confirmations','account_withdrawals',
                          'retained_order_records'):
                cur.execute('DELETE FROM richon.'+table+' WHERE expires_at<=CURRENT_TIMESTAMP')
                counts[table]=cur.rowcount
    return counts


def main():
    parser=argparse.ArgumentParser(description='Delete only expired account-lifecycle records on the reviewed production target.')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        parser.print_help()
        return 2
    try:
        counts=cleanup(expected_database='neondb',expected_user='neondb_owner')
    except Exception:
        print('FAIL: retention cleanup not confirmed; no database details or personal data printed.')
        return 1
    print('PASS: expired account records removed / '+', '.join(k+'='+str(v) for k,v in sorted(counts.items())))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
