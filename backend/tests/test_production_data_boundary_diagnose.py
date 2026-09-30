"""Unit contracts for aggregate-only production data diagnostics."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ops'))

import diagnose_production_data as diag


class FakeCursor:
    def __init__(self):
        self.row=None
    def execute(self,statement):
        text=' '.join(str(statement).split())
        if text=='SELECT current_database(),current_user':
            self.row=('neondb','neondb_owner')
        elif "FROM richon.members" in text and "FILTER(WHERE status='active')" in text:
            self.row=(4,1,2,1)
        elif "FROM richon.auth_identities" in text:
            self.row=(3,2)
        elif "FROM richon.member_marketing_consents" in text:
            self.row=(4,2)
        elif "FROM richon.orders o" in text:
            self.row=(7,2,5)
        elif "FROM richon.enrollment_learners" in text and "member_id IS NOT NULL" in text:
            self.row=(6,4)
        elif "FROM richon.monthly_enrollment_terms" in text and "grant_state='pending'" in text:
            self.row=(2,3,1)
        elif "FROM richon.manual_enrollments" in text and "archived_at IS NULL" in text:
            self.row=(2,1,1)
        elif "FROM richon.course_enrollments e" in text:
            self.row=(1,2,3,1,1,5)
        else:
            singles={
                'SELECT count(*)::bigint FROM richon.member_profiles':4,
                'SELECT count(*)::bigint FROM richon.course_month_rules':2,
                'SELECT count(*)::bigint FROM richon.monthly_enrollments':4,
                'SELECT count(*)::bigint FROM richon.manual_learners':2,
                'SELECT count(*)::bigint FROM richon.manual_terms':2,
                'SELECT count(*)::bigint FROM richon.course_programs':3,
                'SELECT count(*)::bigint FROM richon.course_runs':4,
                'SELECT count(*)::bigint FROM richon.course_sessions':12,
            }
            if text not in singles:
                raise AssertionError(text)
            self.row=(singles[text],)
    def fetchone(self):
        return self.row


def test_inventory_returns_counts_only():
    result=diag.inventory(FakeCursor())
    assert result['members']=={
        'non_withdrawn':5,'active':4,'disabled':1,'withdrawn':2,
        'admins_non_withdrawn':1,'profiles':4,
    }
    assert result['orders']=={'total':7,'pending_payment':2,'linked':5,'unlinked':2}
    assert result['legacy']['monthly_enrollments']==4
    assert result['legacy']['manual_enrollments']==2
    assert result['course_domain']['enrollments']==8
    assert result['course_domain']['member_linked_enrollments']==5


def test_helper_has_no_database_or_cloud_mutation_paths():
    source=(ROOT/'ops'/'diagnose_production_data.py').read_text()
    for pattern in (
        r'\bINSERT\b',r'\bUPDATE\b',r'\bDELETE\b',r'\bTRUNCATE\b',
        r'\bALTER\b',r'\bCREATE\b',r'\bDROP\b',r'\bGRANT\b',r'\bREVOKE\b',
        r'run","services","update',r'update-traffic',r'set-iam-policy',r'add-iam-policy-binding',
    ):
        assert re.search(pattern,source,re.I) is None, pattern
    assert 'conn.read_only=True' in source
    assert 'NO_CUSTOMER_ROWS=YES' in source
    assert 'COUNTS=' in source
    assert 'customer_name' not in source
    assert 'customer_phone' not in source
    assert 'customer_email' not in source
    assert re.search(r'\\bSELECT\\b[^;]*\\bsubject\\b',source,re.I|re.S) is None
