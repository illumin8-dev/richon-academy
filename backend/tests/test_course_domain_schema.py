"""Canonical course-domain schema contract; no customer data and no production DB."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/'migrations'/'015_course_run_foundation.sql').read_text()

def test_program_supports_both_confirmed_access_models():
    assert "access_mode IN ('fixed_months','date_range')" in SQL
    assert "fixed_months BETWEEN 1 AND 36" in SQL
    assert "access_mode='date_range' AND fixed_months IS NULL" in SQL

def test_run_statuses_match_public_cta_contract():
    assert "status IN ('OPEN','WAITLIST','UPCOMING','CLOSED')" in SQL
    for field in ('recruit_opens_at','recruit_closes_at','capacity','default_access_start','default_access_end'):
        assert field in SQL

def test_sessions_are_ordered_and_can_hold_mentor_and_content_link():
    assert 'CREATE TABLE richon.course_sessions' in SQL
    assert 'UNIQUE(run_id,sequence_no)' in SQL
    assert 'mentor_name varchar(80)' in SQL
    assert "content_url ~ '^https://'" in SQL

def test_enrollment_states_are_separate_from_payment():
    assert "status IN ('SCHEDULED','ACTIVE','COMPLETED','CANCELLED','SUSPENDED')" in SQL
    assert "source IN ('ADMIN','LEGACY','INVITE','PAYMENT')" in SQL
    assert 'payment_state' not in re.search(
        r'CREATE TABLE richon\.course_enrollments \((.*?)\);',SQL,re.S).group(1)
    assert 'UNIQUE(run_id,learner_id)' in SQL

def test_legacy_tables_are_not_dropped_or_rewritten():
    upper=SQL.upper()
    assert 'DROP TABLE' not in upper
    assert 'ALTER TABLE RICHON.COURSES' not in upper
    assert 'ALTER TABLE RICHON.MONTHLY_ENROLLMENTS' not in upper
    assert 'DELETE FROM' not in upper and 'TRUNCATE' not in upper and 'INSERT INTO RICHON.COURSE_' not in upper
