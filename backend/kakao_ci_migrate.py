"""Explicit Kakao-CI duplicate-member migration. Never called by portal startup."""
import argparse
import hashlib
from pathlib import Path
import db
from migration_runner import apply_standard_migration

VERSION='014_kakao_ci_dedup'
DIRECTORY=Path(__file__).parent/'migrations'
DEPENDENCIES=('001_pending_orders','002_auth_foundation','007_oauth_handoff',
              '008_login_return_paths','012_oauth_signup_provider_profile',
              '013_oauth_signup_provider_demographics')


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
    )


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed Kakao CI duplicate-member schema.')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        parser.print_help()
        raise SystemExit(2)
    try:
        changed=apply_migration()
    except Exception:
        print('FAIL: Kakao CI migration not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: Kakao CI duplicate-member schema applied.' if changed else
          'PASS: Kakao CI duplicate-member schema already applied.')
