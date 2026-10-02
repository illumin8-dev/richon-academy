"""Historical calendar seed definition only; no network or database access."""
from collections import Counter
from pathlib import Path
import importlib.util
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]
spec=importlib.util.spec_from_file_location('seed_calendar_history_2026',ROOT/'ops'/'seed_calendar_history_2026.py')
seed=importlib.util.module_from_spec(spec);spec.loader.exec_module(seed)


def test_history_seed_matches_owner_month_counts_and_palette():
    assert len(seed.SEED)==76 and len(set(seed.SEED))==76
    counts=Counter(row[1][:7] for row in seed.SEED)
    assert counts=={'2026-06':21,'2026-07':15,'2026-08':12,'2026-09':15,'2026-10':13}
    assert {row[3] for row in seed.SEED}<={seed.B,seed.O,seed.G,seed.R,seed.N,seed.P}
    banners=[row for row in seed.SEED if row[0]=='BANNER']
    assert banners==[('BANNER','2026-09-24','2026-09-26',seed.R,'추석연휴','')]


def test_history_seed_has_expected_october_reference_rows():
    october={row for row in seed.SEED if row[1].startswith('2026-10')}
    assert ('EVENT','2026-10-04',None,seed.R,'리치온 실전투자','멘토 키네스트') in october
    assert ('EVENT','2026-10-06',None,seed.B,'재개발중급반','') in october
    assert ('EVENT','2026-10-08',None,seed.N,'Pre리치온','부동산 투자원칙') in october
    assert ('EVENT','2026-10-29',None,seed.N,'Pre리치온','부동산 기초 및 시장구조') in october
