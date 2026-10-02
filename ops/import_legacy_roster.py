"""Owner-only import of normalized legacy roster data.

The input JSON is generated outside Git and contains customer PII. This helper:
- never creates richon.members or auth identities;
- imports legacy people as enrollment_learners with member_id NULL;
- preserves every normalized workbook row in owner-only DB020 ledger tables;
- corrects Pre-richon 9 by moving existing enrollments to a new reviewed run;
- creates canonical current Richon/Pre9 enrollments only from explicit payload entries.

No Cloud Run, Cloudflare, IAM, Secret Manager, provider, or payment changes.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import UUID, NAMESPACE_URL, uuid5

ROOT=Path(__file__).resolve().parents[1]
MIGRATIONS=ROOT/'backend'/'migrations'
VERSION='020_legacy_roster_import'
CONFIRM='APPLY_LEGACY_ROSTER_IMPORT'


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def checksum(version):
    return hashlib.sha256((MIGRATIONS/(version+'.sql')).read_bytes()).hexdigest()


def parse_date(value):
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError,ValueError):
        raise Stop('invalid_payload_date') from None


def validate_payload(payload):
    need(isinstance(payload,dict) and payload.get('schema_version')==1,'invalid_payload_version')
    need(re.fullmatch(r'[a-f0-9]{64}',str(payload.get('source_sha256',''))),'invalid_source_sha')
    need(isinstance(payload.get('source_name'),str) and payload['source_name'].strip(),'invalid_source_name')
    UUID(str(payload.get('batch_id')))
    learners=payload.get('learners')
    rows=payload.get('rows')
    canonical=payload.get('canonical')
    need(isinstance(learners,list) and isinstance(rows,list) and isinstance(canonical,dict),'invalid_payload_shape')
    need(len(rows)>0 and len(learners)>0,'empty_payload')
    learner_ids=set()
    for learner in learners:
        lid=str(UUID(str(learner['learner_id'])))
        need(lid not in learner_ids,'duplicate_learner_id')
        learner_ids.add(lid)
        need(isinstance(learner.get('name'),str) and learner['name'].strip(),'invalid_learner_name')
        phone=learner.get('phone')
        need(phone is None or re.fullmatch(r'01[016789][0-9]{7,8}',phone),'invalid_learner_phone')
        email=learner.get('email')
        need(email is None or ('@' in email and len(email)<=254),'invalid_learner_email')
    positions=set()
    row_ids=set()
    for row in rows:
        rid=str(UUID(str(row['legacy_row_id'])))
        need(rid not in row_ids,'duplicate_legacy_row_id')
        row_ids.add(rid)
        need(str(UUID(str(row['learner_id']))) in learner_ids,'unknown_row_learner')
        pos=(row.get('source_sheet'),row.get('source_row'))
        need(isinstance(pos[0],str) and pos[0].strip() and isinstance(pos[1],int) and pos[1]>0,'invalid_source_position')
        need(pos not in positions,'duplicate_source_position')
        positions.add(pos)
        joined=parse_date(row.get('joined_on'))
        ended=parse_date(row.get('ended_on'))
        need(joined is None or ended is None or ended>=joined,'invalid_access_window')
        months=row.get('purchase_months')
        need(months is None or (isinstance(months,int) and 1<=months<=36),'invalid_purchase_months')
        amount=row.get('amount_krw')
        need(amount is None or (isinstance(amount,int) and amount>=0),'invalid_amount')
        need(isinstance(row.get('raw_record'),dict),'invalid_raw_record')
    enrollments=canonical.get('enrollments')
    need(isinstance(enrollments,list),'invalid_canonical_enrollments')
    for item in enrollments:
        need(item.get('kind') in ('richon','pre9'),'invalid_enrollment_kind')
        need(str(UUID(str(item['learner_id']))) in learner_ids,'unknown_enrollment_learner')
        start=parse_date(item.get('access_start')); end=parse_date(item.get('access_end'))
        need(start is not None and end is not None and end>=start,'invalid_enrollment_window')
        need(item.get('status') in ('SCHEDULED','ACTIVE','COMPLETED'),'invalid_enrollment_status')
    return payload


def load_payload(path):
    try:
        payload=json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError,UnicodeError):
        raise Stop('payload_read_failed') from None
    return validate_payload(payload)


def db_connect(url):
    try:
        import psycopg
        return psycopg.connect(url)
    except ImportError:
        import psycopg2
        return psycopg2.connect(url)


def verify_schema(cur):
    cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s',(VERSION,))
    need(cur.fetchone()==(checksum(VERSION),),'db020_not_exact')
    cur.execute("""SELECT
      to_regclass('richon.legacy_roster_imports') IS NOT NULL,
      to_regclass('richon.legacy_roster_rows') IS NOT NULL,
      to_regclass('richon.enrollment_learners') IS NOT NULL,
      to_regclass('richon.course_programs') IS NOT NULL,
      to_regclass('richon.course_runs') IS NOT NULL,
      to_regclass('richon.course_enrollments') IS NOT NULL""")
    need(cur.fetchone()==(True,True,True,True,True,True),'required_schema_missing')


def insert_learners(cur,learners):
    for item in learners:
        cur.execute("""INSERT INTO richon.enrollment_learners
          (learner_id,member_id,name,nickname,email,phone)
          VALUES(%s,NULL,%s,%s,%s,%s)
          ON CONFLICT (learner_id) DO UPDATE SET
            name=EXCLUDED.name,nickname=EXCLUDED.nickname,
            email=EXCLUDED.email,phone=EXCLUDED.phone""",
          (item['learner_id'],item['name'],item.get('nickname'),item.get('email'),item.get('phone')))


def insert_ledger(cur,payload):
    cur.execute('SELECT batch_id FROM richon.legacy_roster_imports WHERE source_sha256=%s',
                (payload['source_sha256'],))
    existing=cur.fetchone()
    if existing:
        need(str(existing[0])==str(payload['batch_id']),'source_batch_mismatch')
        return False
    cur.execute("""INSERT INTO richon.legacy_roster_imports
      (batch_id,source_name,source_sha256,row_count,correction_summary)
      VALUES(%s,%s,%s,%s,%s::jsonb)""",
      (payload['batch_id'],payload['source_name'],payload['source_sha256'],
       len(payload['rows']),json.dumps(payload.get('corrections',[]),ensure_ascii=False)))
    for row in payload['rows']:
        cur.execute("""INSERT INTO richon.legacy_roster_rows
          (legacy_row_id,batch_id,learner_id,source_sheet,source_row,course_label,
           purchase_months,amount_krw,payer_name,email_snapshot,contact_snapshot,
           nickname_snapshot,joined_on,ended_on,receipt_issued,raw_record)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
          (row['legacy_row_id'],payload['batch_id'],row['learner_id'],
           row['source_sheet'],row['source_row'],row['course_label'],
           row.get('purchase_months'),row.get('amount_krw'),row.get('payer_name'),
           row.get('email_snapshot'),row.get('contact_snapshot'),row.get('nickname_snapshot'),
           row.get('joined_on'),row.get('ended_on'),row.get('receipt_issued'),
           json.dumps(row['raw_record'],ensure_ascii=False)))
    return True


def ensure_pre9(cur,spec):
    old_run=str(UUID(spec['old_run_id']))
    new_run=str(UUID(spec['new_run_id']))
    cur.execute("""SELECT program_id,cohort_label,recruit_opens_at,recruit_closes_at,capacity,status
                   FROM richon.course_runs WHERE run_id=%s FOR UPDATE""",(old_run,))
    old=cur.fetchone()
    cur.execute('SELECT count(*) FROM richon.course_sessions WHERE run_id=%s',(old_run,))
    need(cur.fetchone()[0]==0,'pre9_old_run_has_sessions')
    cur.execute('SELECT run_id FROM richon.course_runs WHERE run_id=%s',(new_run,))
    new_exists=cur.fetchone() is not None
    if not new_exists:
        need(old is not None and old[0]==spec['program_id'],'pre9_old_run_missing')
        cur.execute("""INSERT INTO richon.course_runs
          (run_id,program_id,cohort_label,starts_on,ends_on,default_access_start,default_access_end,
           recruit_opens_at,recruit_closes_at,capacity,status,price_krw)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
          (new_run,spec['program_id'],spec['cohort_label'],spec['starts_on'],spec['ends_on'],
           spec['access_start'],spec['access_end'],old[2],old[3],old[4],old[5],spec['price_krw']))
    cur.execute("""UPDATE richon.course_enrollments
                   SET run_id=%s,access_start=%s,access_end=%s,updated_at=CURRENT_TIMESTAMP
                   WHERE run_id=%s""",
                (new_run,spec['access_start'],spec['access_end'],old_run))
    cur.execute("""UPDATE richon.course_runs SET archived_at=COALESCE(archived_at,CURRENT_TIMESTAMP),
                   updated_at=CURRENT_TIMESTAMP WHERE run_id=%s""",(old_run,))
    return new_run


def ensure_richon_run(cur,spec):
    cur.execute("""INSERT INTO richon.course_programs
      (program_id,title,access_mode,fixed_months,description)
      VALUES(%s,%s,'date_range',NULL,%s)
      ON CONFLICT (program_id) DO NOTHING""",
      (spec['program_id'],spec['title'],'Legacy/current operational access migrated from roster workbook.'))
    cur.execute("""SELECT title,access_mode,fixed_months FROM richon.course_programs
                   WHERE program_id=%s""",(spec['program_id'],))
    need(cur.fetchone()==(spec['title'],'date_range',None),'richon_program_mismatch')
    cur.execute('SELECT run_id FROM richon.course_runs WHERE run_id=%s',(spec['run_id'],))
    if cur.fetchone() is None:
        cur.execute("""INSERT INTO richon.course_runs
          (run_id,program_id,cohort_label,starts_on,ends_on,default_access_start,default_access_end,
           status,price_krw)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
          (spec['run_id'],spec['program_id'],spec['cohort_label'],spec['starts_on'],spec['ends_on'],
           spec['access_start'],spec['access_end'],spec['status'],spec['price_krw']))
    return str(UUID(spec['run_id']))


def enrollment_id(run_id,learner_id):
    return str(uuid5(NAMESPACE_URL,'https://richonacademy.com/legacy-roster/enrollment/'+
                     str(run_id)+'/'+str(learner_id)))


def insert_canonical_enrollments(cur,payload,pre9_run,richon_run):
    count=0
    for item in payload['canonical']['enrollments']:
        run_id=richon_run if item['kind']=='richon' else pre9_run
        eid=enrollment_id(run_id,item['learner_id'])
        note='legacy roster '+item['source_sheet']+' row '+str(item['source_row'])
        if item.get('note'):
            note+=' / '+item['note']
        cur.execute("""INSERT INTO richon.course_enrollments
          (enrollment_id,run_id,learner_id,status,access_start,access_end,source,note)
          VALUES(%s,%s,%s,%s,%s,%s,'LEGACY',%s)
          ON CONFLICT (run_id,learner_id) DO UPDATE SET
            status=EXCLUDED.status,access_start=EXCLUDED.access_start,
            access_end=EXCLUDED.access_end,note=EXCLUDED.note,updated_at=CURRENT_TIMESTAMP""",
          (eid,run_id,item['learner_id'],item['status'],item['access_start'],item['access_end'],note[:500]))
        count+=1
    return count


def readback(cur,payload,pre9_run,richon_run):
    cur.execute('SELECT count(*) FROM richon.legacy_roster_rows WHERE batch_id=%s',(payload['batch_id'],))
    rows=cur.fetchone()[0]
    cur.execute('SELECT count(DISTINCT learner_id) FROM richon.legacy_roster_rows WHERE batch_id=%s',
                (payload['batch_id'],))
    learners=cur.fetchone()[0]
    cur.execute('SELECT price_krw,starts_on,ends_on,archived_at FROM richon.course_runs WHERE run_id=%s',
                (pre9_run,))
    pre=cur.fetchone()
    cur.execute('SELECT count(*) FROM richon.course_enrollments WHERE run_id=%s',(pre9_run,))
    pre_count=cur.fetchone()[0]
    cur.execute('SELECT count(*) FROM richon.course_enrollments WHERE run_id=%s',(richon_run,))
    richon_count=cur.fetchone()[0]
    need(rows==len(payload['rows']) and learners==len(payload['learners']),'legacy_readback_count_mismatch')
    need(pre is not None and pre[0]==payload['canonical']['pre9']['price_krw']
         and str(pre[1])==payload['canonical']['pre9']['starts_on']
         and str(pre[2])==payload['canonical']['pre9']['ends_on']
         and pre[3] is None,'pre9_readback_mismatch')
    return {'rows':rows,'learners':learners,'pre9_enrollments':pre_count,'richon_enrollments':richon_count}


def execute(url,payload,apply):
    conn=db_connect(url)
    try:
        if not apply:
            try:
                conn.set_session(readonly=True,autocommit=True)
            except TypeError:
                conn.set_session(readonly=True)
                conn.autocommit=True
            cur=conn.cursor()
            verify_schema(cur)
            cur.execute('SELECT count(*) FROM richon.legacy_roster_imports WHERE source_sha256=%s',
                        (payload['source_sha256'],))
            return {'already_imported':bool(cur.fetchone()[0])}
        cur=conn.cursor()
        cur.execute("SET LOCAL statement_timeout='60s'")
        cur.execute("SET LOCAL lock_timeout='10s'")
        cur.execute('SELECT pg_advisory_xact_lock(726426,6)')
        verify_schema(cur)
        insert_learners(cur,payload['learners'])
        inserted=insert_ledger(cur,payload)
        need(inserted,'source_already_imported')
        pre9_run=ensure_pre9(cur,payload['canonical']['pre9'])
        richon_run=ensure_richon_run(cur,payload['canonical']['richon'])
        insert_canonical_enrollments(cur,payload,pre9_run,richon_run)
        result=readback(cur,payload,pre9_run,richon_run)
        conn.commit()
        return result
    except Exception:
        if apply:
            conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--database-url',default=os.getenv('DATABASE_URL'))
    parser.add_argument('--diagnose',action='store_true')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--confirm')
    args=parser.parse_args()
    stage='payload'
    try:
        need(bool(args.database_url),'database_url_required')
        payload=load_payload(args.input)
        print('SOURCE_SHA256='+payload['source_sha256'])
        print('ROWS='+str(len(payload['rows']))+' / LEARNERS='+str(len(payload['learners'])))
        print('MEMBERS_CREATED=0 / AUTH_IDENTITIES_CREATED=0')
        print('CLOUD_RUN_CLOUDFLARE_IAM_SECRET_CHANGES=0')
        if args.diagnose:
            stage='diagnose'
            result=execute(args.database_url,payload,False)
            print('DIAGNOSE=PASS / ALREADY_IMPORTED='+('YES' if result['already_imported'] else 'NO'))
            return 0
        need(args.apply and args.confirm==CONFIRM,'explicit_apply_confirmation_required')
        stage='database'
        result=execute(args.database_url,payload,True)
        print('IMPORT=PASS')
        print('LEGACY_ROWS='+str(result['rows'])+' / LEGACY_LEARNERS='+str(result['learners']))
        print('PRE9_ENROLLMENTS='+str(result['pre9_enrollments'])+
              ' / RICHON_ENROLLMENTS='+str(result['richon_enrollments']))
        print('MEMBERS_CREATED=0 / AUTH_IDENTITIES_CREATED=0')
        return 0
    except (Stop,ValueError,KeyError,Exception,KeyboardInterrupt) as exc:
        code=str(exc) if isinstance(exc,Stop) else type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No customer rows or secrets printed.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
