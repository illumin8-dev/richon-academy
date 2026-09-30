"""Safety contract for the owner-only Pre리치온 9기 creation helper."""
from datetime import date
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ops'))

import create_pre_richon_9 as seed


def test_approved_catalog_values_are_fixed():
    assert seed.PROGRAM_ID=='pre-richon'
    assert seed.PROGRAM_TITLE=='Pre리치온 (프리리치온)'
    assert seed.COHORT=='Pre리치온 9기'
    assert seed.START==date(2026,10,8)
    assert seed.END==date(2026,12,7)
    assert seed.PRICE_KRW==176000
    assert seed.STATUS=='OPEN'
    assert seed.CONFIRM=='CREATE_PRE_RICHON_9'


def test_write_scope_excludes_sessions_enrollments_members_and_orders():
    source=(ROOT/'ops'/'create_pre_richon_9.py').read_text()
    assert re.search(r'INSERT\s+INTO\s+richon\.course_programs',source,re.I)
    assert re.search(r'INSERT\s+INTO\s+richon\.course_runs',source,re.I)
    assert re.search(r'INSERT\s+INTO\s+richon\.course_domain_audit',source,re.I)
    for table in (
        'course_sessions','course_enrollments','enrollment_learners','members',
        'orders','member_order_links','monthly_enrollments','manual_enrollments'
    ):
        assert re.search(r'INSERT\s+INTO\s+richon\.'+table+r'\b',source,re.I) is None
        assert re.search(r'UPDATE\s+richon\.'+table+r'\b',source,re.I) is None
        assert re.search(r'DELETE\s+FROM\s+richon\.'+table+r'\b',source,re.I) is None
    assert 'run","services","update' not in source
    assert 'update-traffic' not in source
    assert 'set-iam-policy' not in source


def test_exact_replay_is_supported_and_schedule_must_stay_empty():
    source=(ROOT/'ops'/'create_pre_richon_9.py').read_text()
    assert 'PRE_RICHON_9=ALREADY_EXACT / DATABASE_CHANGED=NO' in source
    assert 'pre_richon_9_sessions_already_exist' in source
    assert 'pre_richon_9_enrollments_already_exist' in source
    assert 'SESSIONS=0 / ENROLLMENTS=0' in source
    assert "sslmode='verify-full'" not in source  # TLS lives in shared diag.connect().
    assert 'diag.connect' in source
