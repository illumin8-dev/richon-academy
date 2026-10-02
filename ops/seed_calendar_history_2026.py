"""Owner-run insert-only historical calendar seed for 2026-06 through 2026-10.

Source of truth: owner-provided monthly calendar images.
Safety:
- fixed production target
- insert-only: never updates or deletes calendar rows
- refuses to apply while unexpected active rows exist in the seed window
- deterministic UUIDs + exact signature readback
- never prints customer rows or database secrets
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
import sys
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import db
import prepare_account_lifecycle as base
import portal_readiness as ready

CONFIRM='APPLY_CALENDAR_HISTORY_2026'
SEOUL=ZoneInfo('Asia/Seoul')
NAMESPACE=UUID('4d85ef9d-72e5-4e3f-8249-a96e4c719806')
START=datetime(2026,5,31,15,tzinfo=timezone.utc)
END=datetime(2026,10,31,15,tzinfo=timezone.utc)

B='#3978F6';O='#FF9F26';G='#D8BD78';R='#FF5757';N='#00B622';P='#C000DB'

# kind,date,end,color,course_label,content_text
SEED=[
('EVENT','2026-06-01',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-06-03',None,O,'리치온 인테리어',''),
('EVENT','2026-06-04',None,N,'Pre리치온','부동산 투자원칙'),
('EVENT','2026-06-07',None,R,'리치온 스터디','현금흐름'),
('EVENT','2026-06-08',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-06-09',None,B,'재개발중급반',''),
('EVENT','2026-06-10',None,O,'리치온 인테리어',''),
('EVENT','2026-06-11',None,N,'Pre리치온','갭투자'),
('EVENT','2026-06-14',None,R,'리치온 스터디','갭투자'),
('EVENT','2026-06-15',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-06-16',None,B,'재개발중급반',''),
('EVENT','2026-06-17',None,O,'리치온 인테리어',''),
('EVENT','2026-06-18',None,N,'Pre리치온','서울 초기재개발'),
('EVENT','2026-06-21',None,R,'리치온 스터디','서울 초기재개발'),
('EVENT','2026-06-22',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-06-23',None,B,'재개발중급반',''),
('EVENT','2026-06-24',None,O,'리치온 인테리어',''),
('EVENT','2026-06-25',None,N,'Pre리치온','부동산 기초 및 시장구조'),
('EVENT','2026-06-28',None,R,'리치온 스터디','경매'),
('EVENT','2026-06-29',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-06-30',None,B,'재개발중급반',''),

('EVENT','2026-07-01',None,O,'리치온 인테리어',''),
('EVENT','2026-07-05',None,R,'리치온 스터디','청약, 분양권'),
('EVENT','2026-07-06',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-07-08',None,O,'리치온 인테리어',''),
('EVENT','2026-07-09',None,P,'청약 스터디',''),
('EVENT','2026-07-11',None,R,'리치온 스터디','송도 현장임장'),
('EVENT','2026-07-13',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-07-15',None,O,'리치온 인테리어',''),
('EVENT','2026-07-16',None,P,'청약 스터디',''),
('EVENT','2026-07-19',None,R,'리치온 스터디','전국 재개발'),
('EVENT','2026-07-20',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-07-23',None,P,'청약 스터디',''),
('EVENT','2026-07-26',None,R,'리치온 스터디','수익형 경매'),
('EVENT','2026-07-27',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-07-30',None,P,'청약 스터디',''),

('EVENT','2026-08-06',None,N,'Pre리치온','부동산 투자원칙'),
('EVENT','2026-08-09',None,R,'리치온 실전투자','멘토 키네스트'),
('EVENT','2026-08-10',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-08-13',None,N,'Pre리치온','갭투자'),
('EVENT','2026-08-16',None,R,'리치온 실전투자','멘토 후니동산'),
('EVENT','2026-08-17',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-08-20',None,N,'Pre리치온','서울 초기재개발'),
('EVENT','2026-08-23',None,R,'리치온 실전투자','멘토 가위남'),
('EVENT','2026-08-24',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-08-27',None,N,'Pre리치온','부동산 기초 및 시장구조'),
('EVENT','2026-08-30',None,R,'리치온 실전투자','멘토 이루민'),
('EVENT','2026-08-31',None,G,'리치온 아카데미','무료 브리핑'),

('EVENT','2026-09-03',None,N,'Pre리치온','경매 권리분석 및 수익화'),
('EVENT','2026-09-06',None,R,'리치온 실전투자','멘토 키네스트'),
('EVENT','2026-09-07',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-09-10',None,N,'Pre리치온','지방 재개발'),
('EVENT','2026-09-13',None,R,'리치온 실전투자','멘토 재부스'),
('EVENT','2026-09-14',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-09-15',None,B,'재개발중급반',''),
('EVENT','2026-09-17',None,N,'Pre리치온','분양권 전략'),
('EVENT','2026-09-19',None,R,'리치온 현장임장','멘토 가위남'),
('EVENT','2026-09-20',None,R,'리치온 실전투자','멘토 인생곰부'),
('EVENT','2026-09-21',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-09-22',None,B,'재개발중급반',''),
('BANNER','2026-09-24','2026-09-26',R,'추석연휴',''),
('EVENT','2026-09-28',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-09-29',None,B,'재개발중급반',''),

('EVENT','2026-10-04',None,R,'리치온 실전투자','멘토 키네스트'),
('EVENT','2026-10-05',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-10-06',None,B,'재개발중급반',''),
('EVENT','2026-10-08',None,N,'Pre리치온','부동산 투자원칙'),
('EVENT','2026-10-11',None,R,'리치온 실전투자','멘토 후니동산'),
('EVENT','2026-10-12',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-10-15',None,N,'Pre리치온','갭투자'),
('EVENT','2026-10-18',None,R,'리치온 실전투자','멘토 가위남'),
('EVENT','2026-10-19',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-10-22',None,N,'Pre리치온','서울 초기재개발'),
('EVENT','2026-10-25',None,R,'리치온 실전투자','멘토 이루민'),
('EVENT','2026-10-26',None,G,'리치온 아카데미','무료 브리핑'),
('EVENT','2026-10-29',None,N,'Pre리치온','부동산 기초 및 시장구조'),
]

class Stop(Exception): pass
def need(v,code):
    if not v: raise Stop(code)

def signature(row):
    return tuple(row)

def seed_id(row):
    return uuid5(NAMESPACE,'|'.join('' if x is None else str(x) for x in row))

def at_start(value):
    d=date.fromisoformat(value)
    return datetime.combine(d,time.min,tzinfo=SEOUL).astimezone(timezone.utc)

def at_end(value):
    return at_start((date.fromisoformat(value)+timedelta(days=1)).isoformat())

def read_active(cur):
    cur.execute('''SELECT
      CASE WHEN event_type='SPECIAL' AND ends_at IS NOT NULL THEN 'BANNER' ELSE 'EVENT' END,
      to_char(starts_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD'),
      CASE WHEN event_type='SPECIAL' AND ends_at IS NOT NULL
           THEN to_char((ends_at AT TIME ZONE 'Asia/Seoul') - interval '1 day','YYYY-MM-DD') ELSE NULL END,
      color_hex,course_label,content_text
      FROM richon.calendar_events
      WHERE cancelled_at IS NULL AND starts_at >= %s AND starts_at < %s
      ORDER BY starts_at,event_id''',(START,END))
    return [signature(x) for x in cur.fetchall()]

def inspect(cur):
    actual=read_active(cur);expected=list(map(signature,SEED))
    counts=Counter(actual);expected_set=set(expected)
    unexpected=sum(n for row,n in counts.items() if row not in expected_set)
    duplicates=sum(max(0,n-1) for row,n in counts.items() if row in expected_set)
    matched=sum(1 for row in expected if counts[row]>=1)
    return matched,len(expected)-matched,unexpected,duplicates

def apply(owner_url,runtime_url):
    base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
    base.diagnose_connection(runtime_url,ready.ROLE,'runtime')
    try:
        with db._connect(owner_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='30s'")
                cur.execute("SET LOCAL lock_timeout='10s'")
                cur.execute('SELECT pg_advisory_xact_lock(726426,8)')
                need(ready.calendar_schema_ready(cur),'calendar_schema_missing')
                matched,missing,unexpected,duplicates=inspect(cur)
                need(unexpected==0,'unexpected_active_calendar_rows')
                need(duplicates==0,'duplicate_calendar_rows')
                expected_by_id={seed_id(row):row for row in SEED}
                cur.execute('''SELECT event_id,
                  CASE WHEN event_type='SPECIAL' AND ends_at IS NOT NULL THEN 'BANNER' ELSE 'EVENT' END,
                  to_char(starts_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD'),
                  CASE WHEN event_type='SPECIAL' AND ends_at IS NOT NULL
                       THEN to_char((ends_at AT TIME ZONE 'Asia/Seoul') - interval '1 day','YYYY-MM-DD') ELSE NULL END,
                  color_hex,course_label,content_text,cancelled_at IS NOT NULL
                  FROM richon.calendar_events WHERE event_id=ANY(%s)''',(list(expected_by_id),))
                for event_id,kind,event_date,end_date,color,label,content,cancelled in cur.fetchall():
                    need(not cancelled and (kind,event_date,end_date,color,label,content)==expected_by_id[event_id],
                         'seed_id_conflict')
                inserted=0
                active=set(read_active(cur))
                for row in SEED:
                    if row in active: continue
                    kind,event_date,end_date,color,label,content=row
                    cur.execute('''INSERT INTO richon.calendar_events
                      (event_id,event_type,title,starts_at,ends_at,is_public,course_label,content_text,color_hex)
                      VALUES(%s,%s,%s,%s,%s,TRUE,%s,%s,%s)''',
                      (seed_id(row),'SPECIAL' if kind=='BANNER' else 'OTHER',label,at_start(event_date),
                       at_end(end_date) if end_date else None,label,content,color))
                    inserted+=1
                matched2,missing2,unexpected2,duplicates2=inspect(cur)
                need((matched2,missing2,unexpected2,duplicates2)==(len(SEED),0,0,0),'seed_owner_readback_failed')
        with db._connect(runtime_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute('SELECT count(*) FROM richon.calendar_events WHERE cancelled_at IS NULL AND starts_at >= %s AND starts_at < %s',(START,END))
                need(cur.fetchone()==(len(SEED),),'seed_runtime_readback_failed')
        return inserted
    except Stop:
        raise
    except Exception:
        raise Stop('calendar_history_transaction_failed') from None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--diagnose',action='store_true');args=parser.parse_args()
    stage='cloud-target'
    try:
        need(len(SEED)==76 and len(set(SEED))==76,'invalid_seed_definition')
        project=base.gj('projects','describe',base.PROJECT)
        need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
        _,owner_version=base.secret_ref(base.OWNER_SERVICE,base.OWNER_SECRET)
        portal_service,runtime_version=base.secret_ref(base.PORTAL_SERVICE,base.RUNTIME_SECRET)
        print('TARGET=richon-academy / production Neon / calendar history 2026-06..10')
        print('SCOPE=76 owner-approved historical calendar rows / insert-only')
        print('NO_DELETE=YES / NO_UPDATE=YES / NO_DEPLOY=YES / NO_CUSTOMER_ROW_PRINTS=YES')
        stage='secret-access'
        owner_url=base.access(base.OWNER_SECRET,owner_version);runtime_url=base.access(base.RUNTIME_SECRET,runtime_version)
        base.validate_dsn(owner_url,base.OWNER_ROLE);base.validate_dsn(runtime_url,ready.ROLE)
        base.diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
        with db._connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                matched,missing,unexpected,duplicates=inspect(cur)
        print(f'EXPECTED_ROWS={len(SEED)} / MATCHED={matched} / MISSING={missing} / UNEXPECTED_ACTIVE_ROWS={unexpected} / DUPLICATE_MATCHES={duplicates}')
        if args.diagnose:
            print('DIAGNOSE_ONLY=PASS / NO_DATABASE_CHANGES=YES');return 0
        need(unexpected==0,'unexpected_active_calendar_rows')
        need(duplicates==0,'duplicate_calendar_rows')
        if input('Type '+CONFIRM+' to continue: ').strip()!=CONFIRM:
            print('CANCELLED: no database changes made.');return 0
        stage='database'
        inserted=apply(owner_url,runtime_url)
        print(f'CALENDAR_HISTORY_INSERTED={inserted} / TOTAL_ACTIVE={len(SEED)}')
        print('RUNTIME_READBACK=PASS / NO_DELETE=YES / NO_UPDATE=YES / NO_DEPLOY=YES')
        return 0
    except Stop as exc:
        print('STOP='+stage+' / '+str(exc)+' / no secrets or customer rows printed');return 2
    except Exception:
        print('FAIL='+stage+' / no secrets or customer rows printed');return 1

if __name__=='__main__':
    raise SystemExit(main())
