"""Safety contract for the owner-only Pre리치온 9기 admin grant helper."""
from datetime import date
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ops'))

import grant_pre_richon_9_admin as grant


def test_grant_scope_is_exact():
    assert grant.course.PROGRAM_ID=='pre-richon'
    assert grant.course.COHORT=='Pre리치온 9기'
    assert grant.course.START==date(2026,10,8)
    assert grant.course.END==date(2026,12,7)
    assert grant.CONFIRM=='GRANT_PRE_RICHON_9_TO_ADMIN'


def test_only_expected_customer_domain_rows_can_be_written():
    source=(ROOT/'ops'/'grant_pre_richon_9_admin.py').read_text()
    assert re.search(r'INSERT\s+INTO\s+richon\.enrollment_learners',source,re.I)
    assert re.search(r'INSERT\s+INTO\s+richon\.course_enrollments',source,re.I)
    assert re.search(r'INSERT\s+INTO\s+richon\.course_domain_audit',source,re.I)
    for table in (
        'members','member_profiles','orders','member_order_links',
        'course_sessions','monthly_enrollments','manual_enrollments'
    ):
        assert re.search(r'INSERT\s+INTO\s+richon\.'+table+r'\b',source,re.I) is None
        assert re.search(r'UPDATE\s+richon\.'+table+r'\b',source,re.I) is None
        assert re.search(r'DELETE\s+FROM\s+richon\.'+table+r'\b',source,re.I) is None


def test_exact_replay_and_no_row_print_contract():
    source=(ROOT/'ops'/'grant_pre_richon_9_admin.py').read_text()
    assert 'ADMIN_ENROLLMENT=ALREADY_EXACT / DATABASE_CHANGED=NO' in source
    assert 'NO_CUSTOMER_ROWS_PRINTED=YES' in source
    assert 'active_admin_count_not_one' in source
    assert 'existing_pre_richon_9_enrollment_conflict' in source
    assert 'SESSIONS=0' in source
    assert 'print(row' not in source
    assert 'print(admin_id' not in source
