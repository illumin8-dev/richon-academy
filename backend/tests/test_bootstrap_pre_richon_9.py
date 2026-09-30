"""Contracts for the guarded Pre리치온 9 production bootstrap."""
from datetime import date
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ops'))

import bootstrap_pre_richon_9 as boot


def test_pre_richon_9_plan_is_exact():
    assert boot.CONFIRM=='APPLY_PRE_RICHON_9'
    assert boot.PROGRAM_ID=='pre-richon'
    assert boot.PROGRAM_TITLE=='Pre리치온 (프리리치온)'
    assert boot.COHORT=='Pre리치온 9기'
    assert boot.PRICE_KRW==132000
    assert boot.START_ON==date(2026,10,1)
    assert boot.RUN_END==date(2026,11,30)
    assert boot.ACCESS_START==date(2026,10,1)
    assert boot.ACCESS_END==date(2026,11,30)
    assert '7주 온라인 강의 + 8주차 현장 임장' in boot.PROGRAM_DESCRIPTION
    assert '추후 공지' in boot.PROGRAM_DESCRIPTION


def test_only_first_seven_online_sessions_are_created():
    assert len(boot.SESSIONS)==7
    assert [row[0] for row in boot.SESSIONS]==list(range(1,8))
    assert [row[1][:10] for row in boot.SESSIONS]==[
        '2026-10-01','2026-10-08','2026-10-15','2026-10-22',
        '2026-10-29','2026-11-05','2026-11-12',
    ]
    assert all(row[1][11:16]=='21:00' and row[2][11:16]=='23:00' for row in boot.SESSIONS)
    assert all(row[1].endswith('+09:00') and row[2].endswith('+09:00') for row in boot.SESSIONS)
    assert boot.SESSIONS[-1][3:] == ('경매 권리분석 및 수익화','인생곰부')
    assert not any(row[0]==8 for row in boot.SESSIONS)


def test_payloads_use_two_month_fixed_access_and_no_recruit_invention():
    p=boot.program_body()
    assert p.access_mode=='fixed_months' and p.fixed_months==2
    r=boot.run_body()
    assert r.program_id=='pre-richon'
    assert r.cohort_label=='Pre리치온 9기'
    assert r.price_krw==132000
    assert r.starts_on==date(2026,10,1)
    assert r.ends_on==date(2026,11,30)
    assert r.default_access_start==date(2026,10,1)
    assert r.default_access_end==date(2026,11,30)
    assert r.recruit_opens_at is None and r.recruit_closes_at is None
    assert r.capacity is None
    assert r.status=='OPEN'


def test_bootstrap_uses_application_mutation_path_not_direct_write_sql():
    source=(ROOT/'ops'/'bootstrap_pre_richon_9.py').read_text()
    assert 'store.mutate' in source
    assert 'richon_portal_login' in source
    for pattern in (
        r'INSERT\s+INTO\s+richon\.',
        r'UPDATE\s+richon\.',
        r'DELETE\s+FROM\s+richon\.',
        r'TRUNCATE\s+richon\.',
        r'ALTER\s+TABLE',
        r'CREATE\s+TABLE',
        r'GRANT\s+',
        r'REVOKE\s+',
    ):
        assert re.search(pattern,source,re.I) is None, pattern
    assert "parser.add_argument('--apply',action='store_true')" in source
    assert "input('Type '+CONFIRM+' to continue: ')" in source
    assert 'TARGET_MEMBER=SOLE_ACTIVE_ADMIN' in source
    assert 'IDENTIFIER_NOT_PRINTED=YES' in source


def test_request_ids_are_deterministic_and_distinct():
    values=[
        boot.request_id('program'),
        boot.request_id('run'),
        *(boot.request_id('session-'+str(i)) for i in range(1,8)),
        boot.request_id('enrollment-sole-active-admin'),
    ]
    assert len(set(values))==10
    assert values==[
        boot.request_id('program'),
        boot.request_id('run'),
        *(boot.request_id('session-'+str(i)) for i in range(1,8)),
        boot.request_id('enrollment-sole-active-admin'),
    ]
