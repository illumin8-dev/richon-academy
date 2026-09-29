"""Canonical course/run/session/enrollment reads and admin writes.

Legacy monthly/manual records remain untouched. Member linkage is explicit only.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import UUID, uuid4

import auth_core
from portal_store import read_cursor, _literal_search


class Rejected(Exception):
    def __init__(self, code='record_conflict', status=409):
        self.code,self.status=code,status
        super().__init__(code)


@contextmanager
def transaction(actor):
    with auth_core._transaction() as cur:
        cur.execute('SELECT role,status FROM richon.members WHERE member_id=%s FOR SHARE',(actor,))
        if cur.fetchone()!=('admin','active'):
            raise Rejected('admin_required',403)
        yield cur


def _rows(cur):
    names=[x.name for x in cur.description]
    return [dict(zip(names,row,strict=True)) for row in cur.fetchall()]


def _audit(cur,actor,request_id,fingerprint,operation,entity,reason,result):
    cur.execute('''INSERT INTO richon.course_domain_audit
      (event_id,actor_id,request_id,fingerprint,operation,entity_id,reason,result)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)''',
      (uuid4(),actor,request_id,fingerprint,operation,str(entity),reason,json.dumps(result,ensure_ascii=True)))


def mutate(actor,operation,payload):
    data=payload.model_dump(mode='json')
    request_id=str(data['request_id'])
    fingerprint=hashlib.sha256(json.dumps([operation,data],sort_keys=True,ensure_ascii=True).encode()).hexdigest()
    key=int.from_bytes(hashlib.sha256((str(actor)+request_id).encode()).digest()[:8],'big',signed=True)
    try:
        with transaction(actor) as cur:
            cur.execute('SELECT pg_advisory_xact_lock(%s)',(key,))
            cur.execute('SELECT fingerprint,result FROM richon.course_domain_audit WHERE actor_id=%s AND request_id=%s',
                        (actor,request_id))
            prior=cur.fetchone()
            if prior:
                if prior[0]!=fingerprint: raise Rejected('request_key_reused')
                result=prior[1]
            else:
                handler={
                    'program.create':_program_create,'program.update':_program_update,
                    'run.create':_run_create,'run.update':_run_update,
                    'session.create':_session_create,
                    'enrollment.grant':_enrollment_grant,'enrollment.cancel':_enrollment_cancel,
                }.get(operation)
                if handler is None: raise Rejected('unsupported_operation',404)
                result=handler(cur,actor,payload)
                _audit(cur,actor,request_id,fingerprint,operation,
                       result.get('enrollment_id',result.get('run_id',result.get('program_id',result.get('session_id','')))),
                       payload.reason,result)
    except Rejected:
        raise
    except Exception as exc:
        if getattr(exc,'sqlstate',None) in {'23505','23503','23514','P0001','40001','40P01'}:
            raise Rejected('record_conflict') from None
        raise
    return result


def _program_create(cur,actor,body):
    cur.execute('''INSERT INTO richon.course_programs
      (program_id,title,description,access_mode,fixed_months)
      VALUES(%s,%s,%s,%s,%s)
      RETURNING program_id,version''',
      (body.program_id,body.title,body.description,body.access_mode,body.fixed_months))
    pid,version=cur.fetchone()
    return {'program_id':pid,'version':version}


def _program_update(cur,actor,body):
    cur.execute('SELECT version FROM richon.course_programs WHERE program_id=%s FOR UPDATE',(body.program_id,))
    row=cur.fetchone()
    if row is None: raise Rejected('program_not_found',404)
    if row[0]!=body.version: raise Rejected('stale_record')
    cur.execute('''UPDATE richon.course_programs
      SET title=%s,description=%s,archived_at=%s,version=version+1,updated_at=CURRENT_TIMESTAMP
      WHERE program_id=%s RETURNING version''',
      (body.title,body.description,datetime.now(timezone.utc) if body.archived else None,body.program_id))
    return {'program_id':body.program_id,'version':cur.fetchone()[0],'archived':body.archived}


def _run_create(cur,actor,body):
    cur.execute('SELECT archived_at FROM richon.course_programs WHERE program_id=%s FOR SHARE',(body.program_id,))
    row=cur.fetchone()
    if row is None: raise Rejected('program_not_found',404)
    if row[0] is not None: raise Rejected('program_archived')
    rid=uuid4()
    cur.execute('''INSERT INTO richon.course_runs
      (run_id,program_id,cohort_label,starts_on,ends_on,default_access_start,default_access_end,
       recruit_opens_at,recruit_closes_at,capacity,status,price_krw)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      RETURNING version''',
      (rid,body.program_id,body.cohort_label,body.starts_on,body.ends_on,
       body.default_access_start,body.default_access_end,body.recruit_opens_at,
       body.recruit_closes_at,body.capacity,body.status,body.price_krw))
    return {'run_id':str(rid),'program_id':body.program_id,'version':cur.fetchone()[0]}


def _run_update(cur,actor,body):
    cur.execute('SELECT version FROM richon.course_runs WHERE run_id=%s FOR UPDATE',(body.run_id,))
    row=cur.fetchone()
    if row is None: raise Rejected('run_not_found',404)
    if row[0]!=body.version: raise Rejected('stale_record')
    cur.execute('''UPDATE richon.course_runs
      SET cohort_label=%s,recruit_opens_at=%s,recruit_closes_at=%s,capacity=%s,status=%s,
          price_krw=%s,archived_at=%s,version=version+1,updated_at=CURRENT_TIMESTAMP
      WHERE run_id=%s RETURNING version''',
      (body.cohort_label,body.recruit_opens_at,body.recruit_closes_at,body.capacity,body.status,
       body.price_krw,datetime.now(timezone.utc) if body.archived else None,body.run_id))
    return {'run_id':str(body.run_id),'version':cur.fetchone()[0],'archived':body.archived}


def _session_create(cur,actor,body):
    cur.execute('SELECT 1 FROM richon.course_runs WHERE run_id=%s AND archived_at IS NULL FOR SHARE',(body.run_id,))
    if cur.fetchone() is None: raise Rejected('run_not_found',404)
    sid=uuid4()
    cur.execute('''INSERT INTO richon.course_sessions
      (session_id,run_id,sequence_no,title,mentor_name,starts_at,ends_at,video_url,material_url)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING version''',
      (sid,body.run_id,body.sequence_no,body.title,body.mentor_name,body.starts_at,body.ends_at,
       body.video_url,body.material_url))
    return {'session_id':str(sid),'run_id':str(body.run_id),'version':cur.fetchone()[0]}


def _resolve_learner(cur,body):
    if body.learner_id is not None:
        cur.execute('SELECT learner_id FROM richon.enrollment_learners WHERE learner_id=%s FOR SHARE',(body.learner_id,))
        if cur.fetchone() is None: raise Rejected('learner_not_found',404)
        return body.learner_id
    if body.member_id is not None:
        cur.execute('''SELECT m.display_name,p.name,p.email,p.phone
          FROM richon.members m LEFT JOIN richon.member_profiles p ON p.member_id=m.member_id
          WHERE m.member_id=%s AND m.status='active' FOR SHARE OF m''',(body.member_id,))
        row=cur.fetchone()
        if row is None: raise Rejected('member_not_found',404)
        cur.execute('SELECT learner_id FROM richon.enrollment_learners WHERE member_id=%s FOR SHARE',(body.member_id,))
        existing=cur.fetchone()
        if existing:return existing[0]
        lid=uuid4()
        cur.execute('''INSERT INTO richon.enrollment_learners(learner_id,member_id,name,email,phone)
          VALUES(%s,%s,%s,%s,%s)''',(lid,body.member_id,row[1] or row[0],row[2],row[3]))
        return lid
    lid=uuid4();p=body.profile
    cur.execute('''INSERT INTO richon.enrollment_learners(learner_id,name,email,phone)
      VALUES(%s,%s,%s,%s)''',(lid,p.name,p.email,p.phone))
    return lid


def _enrollment_grant(cur,actor,body):
    lid=_resolve_learner(cur,body)
    cur.execute('''SELECT p.access_mode,p.fixed_months,r.default_access_start,r.default_access_end,
                          p.archived_at,r.archived_at
      FROM richon.course_runs r JOIN richon.course_programs p USING(program_id)
      WHERE r.run_id=%s FOR SHARE OF r,p''',(body.run_id,))
    row=cur.fetchone()
    if row is None: raise Rejected('run_not_found',404)
    mode,months,default_start,default_end,program_archived,run_archived=row
    if program_archived is not None or run_archived is not None: raise Rejected('course_not_available')
    if mode=='fixed_months':
        if body.access_start is not None and (body.access_start!=default_start or body.access_end!=default_end):
            raise Rejected('fixed_access_window',422)
        access_start,access_end=default_start,default_end
    else:
        access_start=body.access_start or default_start
        access_end=body.access_end or default_end
    eid=uuid4()
    cur.execute('''INSERT INTO richon.course_enrollments
      (enrollment_id,run_id,learner_id,status,access_start,access_end,source,note)
      VALUES(%s,%s,%s,
        CASE WHEN CURRENT_DATE<%s THEN 'SCHEDULED'
             WHEN CURRENT_DATE>%s THEN 'COMPLETED' ELSE 'ACTIVE' END,
        %s,%s,'ADMIN',%s)
      RETURNING status,version''',
      (eid,body.run_id,lid,access_start,access_end,access_start,access_end,body.note))
    status,version=cur.fetchone()
    return {'enrollment_id':str(eid),'learner_id':str(lid),'run_id':str(body.run_id),
            'status':status,'version':version,'source':'ADMIN'}


def _enrollment_cancel(cur,actor,body):
    cur.execute('SELECT version,status FROM richon.course_enrollments WHERE enrollment_id=%s FOR UPDATE',(body.enrollment_id,))
    row=cur.fetchone()
    if row is None: raise Rejected('enrollment_not_found',404)
    if row[0]!=body.version: raise Rejected('stale_record')
    if row[1]=='CANCELLED':
        raise Rejected('already_cancelled')
    cur.execute('''UPDATE richon.course_enrollments
      SET status='CANCELLED',cancelled_at=CURRENT_TIMESTAMP,suspended_at=NULL,
          version=version+1,updated_at=CURRENT_TIMESTAMP
      WHERE enrollment_id=%s RETURNING version''',(body.enrollment_id,))
    return {'enrollment_id':str(body.enrollment_id),'version':cur.fetchone()[0],'status':'CANCELLED'}


def programs(limit=100,offset=0,include_archived=False):
    with read_cursor() as cur:
        cur.execute('''SELECT program_id,title,description,access_mode,fixed_months,
              (archived_at IS NOT NULL) AS archived,version,created_at,updated_at
          FROM richon.course_programs
          WHERE (%s OR archived_at IS NULL)
          ORDER BY archived_at NULLS FIRST,title,program_id LIMIT %s OFFSET %s''',
          (include_archived,limit+1,offset))
        rows=_rows(cur)
    return {'items':rows[:limit],'limit':limit,'offset':offset,'has_more':len(rows)>limit}


def runs(program_id=None,limit=100,offset=0,include_archived=False):
    with read_cursor() as cur:
        cur.execute('''SELECT r.run_id,r.program_id,p.title AS program_title,r.cohort_label,r.starts_on,r.ends_on,
              r.default_access_start,r.default_access_end,r.recruit_opens_at,r.recruit_closes_at,
              r.capacity,r.status,r.price_krw,(r.archived_at IS NOT NULL) AS archived,r.version,
              (SELECT count(*) FROM richon.course_enrollments e WHERE e.run_id=r.run_id AND e.status<>'CANCELLED') AS enrollment_count
          FROM richon.course_runs r JOIN richon.course_programs p USING(program_id)
          WHERE (%s::text IS NULL OR r.program_id=%s) AND (%s OR r.archived_at IS NULL)
          ORDER BY r.starts_on DESC,r.run_id DESC LIMIT %s OFFSET %s''',
          (program_id,program_id,include_archived,limit+1,offset))
        rows=_rows(cur)
    return {'items':rows[:limit],'limit':limit,'offset':offset,'has_more':len(rows)>limit}


def enrollments(run_id=None,limit=50,offset=0):
    with read_cursor() as cur:
        cur.execute('''SELECT e.enrollment_id,e.run_id,e.learner_id,l.member_id,l.name,
              CASE WHEN l.phone IS NULL THEN NULL ELSE left(l.phone,3)||'-****-'||right(l.phone,4) END AS phone_masked,
              CASE WHEN l.email IS NULL THEN NULL ELSE left(split_part(l.email,'@',1),1)||'***@'||split_part(l.email,'@',2) END AS email_masked,
              p.title AS program_title,r.cohort_label,e.access_start,e.access_end,e.source,e.note,e.version,
              CASE WHEN e.status IN ('CANCELLED','SUSPENDED') THEN e.status
                   WHEN CURRENT_DATE<e.access_start THEN 'SCHEDULED'
                   WHEN CURRENT_DATE>e.access_end THEN 'COMPLETED' ELSE 'ACTIVE' END AS status
          FROM richon.course_enrollments e
          JOIN richon.enrollment_learners l USING(learner_id)
          JOIN richon.course_runs r USING(run_id) JOIN richon.course_programs p USING(program_id)
          WHERE (%s::uuid IS NULL OR e.run_id=%s)
          ORDER BY e.created_at DESC,e.enrollment_id DESC LIMIT %s OFFSET %s''',
          (run_id,run_id,limit+1,offset))
        rows=_rows(cur)
    return {'items':rows[:limit],'limit':limit,'offset':offset,'has_more':len(rows)>limit}


def targets(q,limit=20):
    phone=re.sub(r'[ ()-]','',q)
    if phone.startswith('+82'):phone='0'+phone[3:]
    like=_literal_search(q)
    with read_cursor() as cur:
        cur.execute('''WITH candidates AS (
          SELECT 'learner'::text AS target_type,l.learner_id,l.member_id,l.name,l.phone,l.email,l.created_at
            FROM richon.enrollment_learners l
           WHERE l.name ILIKE %(like)s ESCAPE E'\\' OR l.phone=%(phone)s OR lower(l.email)=lower(%(exact)s)
          UNION ALL
          SELECT 'member'::text,NULL::uuid,m.member_id,coalesce(p.name,m.display_name),p.phone,p.email,m.created_at
            FROM richon.members m LEFT JOIN richon.member_profiles p ON p.member_id=m.member_id
           WHERE m.status='active' AND NOT EXISTS(
                 SELECT 1 FROM richon.enrollment_learners l WHERE l.member_id=m.member_id)
             AND (coalesce(p.name,m.display_name) ILIKE %(like)s ESCAPE E'\\'
                  OR p.phone=%(phone)s OR lower(p.email)=lower(%(exact)s) OR m.member_id::text=%(exact)s)
        )
        SELECT target_type,learner_id,member_id,name,
          CASE WHEN phone IS NULL THEN NULL ELSE left(phone,3)||'-****-'||right(phone,4) END AS phone_masked,
          CASE WHEN email IS NULL THEN NULL ELSE left(split_part(email,'@',1),1)||'***@'||split_part(email,'@',2) END AS email_masked
        FROM candidates ORDER BY created_at DESC LIMIT %(limit)s''',
        {'like':like,'phone':phone,'exact':q,'limit':limit})
        return _rows(cur)


def my_courses(member_id:UUID,limit=20,offset=0):
    with read_cursor() as cur:
        cur.execute('''SELECT e.enrollment_id,e.run_id,p.program_id,p.title AS program_title,p.description,
             r.cohort_label,r.starts_on,r.ends_on,e.access_start,e.access_end,e.source,
             CASE WHEN e.status IN ('CANCELLED','SUSPENDED') THEN e.status
                  WHEN CURRENT_DATE<e.access_start THEN 'SCHEDULED'
                  WHEN CURRENT_DATE>e.access_end THEN 'COMPLETED' ELSE 'ACTIVE' END AS status,
             coalesce((SELECT jsonb_agg(jsonb_build_object(
                 'session_id',s.session_id,'sequence_no',s.sequence_no,'title',s.title,'mentor_name',s.mentor_name,
                 'starts_at',s.starts_at,'ends_at',s.ends_at,
                 'video_url',CASE WHEN CURRENT_DATE BETWEEN e.access_start AND e.access_end
                                      AND e.status NOT IN ('CANCELLED','SUSPENDED')
                                  THEN coalesce(s.video_url,s.content_url) END,
                 'material_url',CASE WHEN CURRENT_DATE BETWEEN e.access_start AND e.access_end
                                         AND e.status NOT IN ('CANCELLED','SUSPENDED')
                                     THEN s.material_url END
               ) ORDER BY s.sequence_no)
               FROM richon.course_sessions s WHERE s.run_id=e.run_id AND s.cancelled_at IS NULL),'[]'::jsonb) AS sessions
          FROM richon.course_enrollments e
          JOIN richon.enrollment_learners l USING(learner_id)
          JOIN richon.course_runs r USING(run_id) JOIN richon.course_programs p USING(program_id)
          WHERE l.member_id=%s AND e.status<>'CANCELLED'
          ORDER BY e.access_end DESC,e.created_at DESC LIMIT %s OFFSET %s''',
          (member_id,limit+1,offset))
        rows=_rows(cur)
    return {'items':rows[:limit],'limit':limit,'offset':offset,'has_more':len(rows)>limit}
