"""Explicit canonical course-domain migration. Never runs at application startup."""
import argparse
import hashlib
from pathlib import Path
import db
from migration_runner import apply_standard_migration

VERSION='015_course_run_foundation'
DIRECTORY=Path(__file__).parent/'migrations'
DEPENDENCIES=('001_pending_orders','002_auth_foundation','003_portal_read_models',
              '004_monthly_enrollments','005_manual_registry','009_member_profiles',
              '014_kakao_ci_dedup')

def checksum(name):
    return hashlib.sha256((DIRECTORY/(name+'.sql')).read_bytes()).hexdigest()


def checksum_variant(name, recorded):
    """Classify only known byte-level representations; never expose raw hashes."""
    if not isinstance(recorded,str):
        return 'MISSING'
    raw=(DIRECTORY/(name+'.sql')).read_bytes()
    lf=raw.replace(b'\r\n',b'\n')
    base=lf[:-1] if lf.endswith(b'\n') else lf
    crlf=lf.replace(b'\n',b'\r\n')
    crlf_base=crlf[:-2] if crlf.endswith(b'\r\n') else crlf
    variants=[
        ('EXACT',raw),
        ('LF',lf),
        ('LF_NO_FINAL_NEWLINE',base),
        ('CRLF',crlf),
        ('CRLF_NO_FINAL_NEWLINE',crlf_base),
        ('UTF8_BOM',b'\xef\xbb\xbf'+lf),
        ('UTF8_BOM_CRLF',b'\xef\xbb\xbf'+crlf),
    ]
    for label,data in variants:
        if hashlib.sha256(data).hexdigest()==recorded:
            return label
    return 'UNKNOWN'


def apply_migration(*, connection_url=None):
    return apply_standard_migration(
        db_module=db,
        directory=DIRECTORY,
        version=VERSION,
        dependencies=DEPENDENCIES,
        checksum=checksum,
        connection_url=connection_url,
        dependency_error_with_version=True,
    )

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Apply reviewed course/run/session/enrollment schema.')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not args.apply:
        parser.print_help(); raise SystemExit(2)
    try:
        changed=apply_migration()
    except Exception:
        print('FAIL: course-domain migration not confirmed; no secrets printed.')
        raise SystemExit(1) from None
    print('PASS: canonical course domain created.' if changed else
          'PASS: canonical course domain already applied.')
