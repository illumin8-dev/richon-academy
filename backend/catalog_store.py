"""Admin catalog store. New source of truth only; legacy monthly records are untouched."""
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID,uuid4
import auth_core
from monthly_store import _rows
from portal_store import read_cursor

class Rejected(Exception):
    def __init__(self,code='catalog_conflict',status=409):
        self.code,self.status=code,status
        super().__init__(code)

@contextmanager
def transaction(actor):
    with auth_core._transaction() as cur:
        cur.execute('SELECT role,status FROM richon.members WHERE member_id=%s FOR SHARE',(actor,))
        if cur.fetchone()!=('admin','active'): raise Rejected('admin_required',403)
        yield cur

def _audit(cur,actor,operation,entity,reason,result,request_id,fingerprint):
    cur.execute("""INSERT INTO richon.course_catalog_audit
      (event_id,actor_id,request_id,fingerprint,operation,entity_id,reason,result)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
      (uuid4(),actor,request_id,fingerprint,operation,str(entity),reason,json.dumps(result)))

def _policy(cur,program_id):
    cur.execute('SELECT access_kind,fixed_months,archived_at FROM richon.course_programs WHERE program_id=%s FOR SHARE',(program_id,))
    row=cur.fetchone()
    if not row: raise Rejected('program_not_found',404)
    if row[2] is not None: raise Rejected('program_archived')
    return row[0],row[1]

def _validate_run_access(cur,program_id,start,end):
    kind,months=_policy(cur,program_id)
    if kind=='fixed_months':
        if start is None or end is None: raise Rejected('fixed_access_period_required',422)
        cur.execute("SELECT (%s::date + make_interval(months=>%s) - interval '1 day')::date",(start,months))
        if end!=cur.fetchone()[0]: raise Rejected('fixed_access_period_mismatch',422)
    return kind,months

def mutate(actor,operation,payload):
    data=payload.model_dump(mode='json')
    fingerprint=hashlib.sha256(json.dumps([operation,data],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    key=int.from_bytes(hashlib.sha256((str(actor)+data['request_id']).encode()).digest()[:8],'big',signed=True)
    try:
        with transaction(actor) as cur:
            cur.execute('SELECT pg_advisory_xact_lock(%s)',(key,))
            cur.execute('SELECT fingerprint,result FROM richon.course_catalog_audit WHERE actor_id=%s AND request_id=%s',
                        (actor,data['request_id']))
            prior=cur.fetchone()
            if prior:
                if prior[0]!=fingerprint: raise Rejected('request_key_reused')
                return prior[1]
            handler={
                'program.create':create_program,'program.update':update_program,
                'run.create':create_run,'run.update':update_run,
                'session.create':create_session,'session.update':update_session,
            }[operation]
            result=handler(cur,payload)
            _audit(cur,actor,operation,next(iter([result.get(k) for k in ('program_id','run_id','session_id') if result.get(k)]),''),
                   payload.reason,result,payload.request_id,fingerprint)
        return result
    except Rejected: raise
    except Exception as exc:
        if getattr(exc,'sqlstate',None) in {'23505','23503','23514','P0001','40001','40P01'}:
            raise Rejected('catalog_conflict') from None
        raise

def create_program(cur,body):
    pid=uuid4()
    cur.execute("""INSERT INTO richon.course_programs
      (program_id,title,description,access_kind,fixed_months)
      VALUES(%s,%s,%s,%s,%s) RETURNING version""",
      (pid,body.title,body.description,body.access_kind,body.fixed_months))
    return {'program_id':str(pid),'version':cur.fetchone()[0]}

def update_program(cur,body):
    pid=UUID(body.program_id)
    cur.execute('SELECT access_kind,fixed_months FROM richon.course_programs WHERE program_id=%s FOR UPDATE',(pid,))
    old=cur.fetchone()
    if not old: raise Rejected('program_not_found',404)
    if old!=(body.access_kind,body.fixed_months):
        cur.execute('SELECT 1 FROM richon.course_runs WHERE program_id=%s LIMIT 1',(pid,))
        if cur.fetchone(): raise Rejected('program_access_policy_in_use')
    cur.execute("""UPDATE richon.course_programs
      SET title=%s,description=%s,access_kind=%s,fixed_months=%s,
          archived_at=%s,version=version+1,updated_at=CURRENT_TIMESTAMP
      WHERE program_id=%s AND version=%s RETURNING version""",
      (body.title,body.description,body.access_kind,body.fixed_months,
       datetime.now(timezone.utc) if body.archived else None,pid,body.version))
    row=cur.fetchone()
    if not row: raise Rejected('stale_program')
    return {'program_id':body.program_id,'version':row[0],'archived':body.archived}

def create_run(cur,body):
    pid=UUID(body.program_id);_validate_run_access(cur,pid,body.default_access_start,body.default_access_end)
    rid=uuid4()
    cur.execute("""INSERT INTO richon.course_runs
      (run_id,program_id,cohort,status,starts_on,ends_on,default_access_start,default_access_end,
       recruitment_open_at,recruitment_close_at,capacity,price_krw)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING version""",
      (rid,pid,body.cohort,body.status,body.starts_on,body.ends_on,body.default_access_start,body.default_access_end,
       body.recruitment_open_at,body.recruitment_close_at,body.capacity,body.price_krw))
    return {'run_id':str(rid),'program_id':body.program_id,'version':cur.fetchone()[0]}

def update_run(cur,body):
    rid=UUID(body.run_id)
    cur.execute('SELECT program_id FROM richon.course_runs WHERE run_id=%s FOR UPDATE',(rid,))
    row=cur.fetchone()
    if not row: raise Rejected('run_not_found',404)
    _validate_run_access(cur,row[0],body.default_access_start,body.default_access_end)
    cur.execute("""UPDATE richon.course_runs SET
      cohort=%s,status=%s,starts_on=%s,ends_on=%s,default_access_start=%s,default_access_end=%s,
      recruitment_open_at=%s,recruitment_close_at=%s,capacity=%s,price_krw=%s,
      archived_at=%s,version=version+1,updated_at=CURRENT_TIMESTAMP
      WHERE run_id=%s AND version=%s RETURNING version""",
      (body.cohort,body.status,body.starts_on,body.ends_on,body.default_access_start,body.default_access_end,
       body.recruitment_open_at,body.recruitment_close_at,body.capacity,body.price_krw,
       datetime.now(timezone.utc) if body.archived else None,rid,body.version))
    row=cur.fetchone()
    if not row: raise Rejected('stale_run')
    return {'run_id':body.run_id,'version':row[0],'archived':body.archived}

def _run(cur,run_id):
    cur.execute("""SELECT r.run_id FROM richon.course_runs r JOIN richon.course_programs p USING(program_id)
      WHERE r.run_id=%s AND r.archived_at IS NULL AND p.archived_at IS NULL FOR SHARE OF r,p""",(run_id,))
    if not cur.fetchone(): raise Rejected('run_not_found',404)

def create_session(cur,body):
    rid=UUID(body.run_id);_run(cur,rid);sid=uuid4()
    cur.execute("""INSERT INTO richon.course_sessions
      (session_id,run_id,sequence_no,title,mentor_name,starts_at,ends_at,content_url)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING version""",
      (sid,rid,body.sequence_no,body.title,body.mentor_name,body.starts_at,body.ends_at,body.content_url))
    return {'session_id':str(sid),'run_id':body.run_id,'version':cur.fetchone()[0]}

def update_session(cur,body):
    sid=UUID(body.session_id)
    cur.execute('SELECT run_id FROM richon.course_sessions WHERE session_id=%s FOR UPDATE',(sid,))
    row=cur.fetchone()
    if not row: raise Rejected('session_not_found',404)
    _run(cur,row[0])
    cur.execute("""UPDATE richon.course_sessions SET
      sequence_no=%s,title=%s,mentor_name=%s,starts_at=%s,ends_at=%s,content_url=%s,
      archived_at=%s,version=version+1,updated_at=CURRENT_TIMESTAMP
      WHERE session_id=%s AND version=%s RETURNING version""",
      (body.sequence_no,body.title,body.mentor_name,body.starts_at,body.ends_at,body.content_url,
       datetime.now(timezone.utc) if body.archived else None,sid,body.version))
    row=cur.fetchone()
    if not row: raise Rejected('stale_session')
    return {'session_id':body.session_id,'version':row[0],'archived':body.archived}

def programs(include_archived=False):
    with read_cursor() as cur:
        cur.execute("""SELECT program_id,title,description,access_kind,fixed_months,version,
          (archived_at IS NOT NULL) AS archived,created_at,updated_at
          FROM richon.course_programs
          WHERE (%s OR archived_at IS NULL)
          ORDER BY archived_at NULLS FIRST,title,program_id""",(include_archived,))
        return _rows(cur)

def runs(program_id=None,include_archived=False):
    with read_cursor() as cur:
        cur.execute("""SELECT r.run_id,r.program_id,p.title AS program_title,r.cohort,r.status,
          r.starts_on,r.ends_on,r.default_access_start,r.default_access_end,
          r.recruitment_open_at,r.recruitment_close_at,r.capacity,r.price_krw,r.version,
          (r.archived_at IS NOT NULL) AS archived
          FROM richon.course_runs r JOIN richon.course_programs p USING(program_id)
          WHERE (%s::uuid IS NULL OR r.program_id=%s::uuid) AND (%s OR r.archived_at IS NULL)
          ORDER BY r.starts_on DESC,r.run_id""",(program_id,program_id,include_archived))
        return _rows(cur)

def sessions(run_id,include_archived=False):
    with read_cursor() as cur:
        cur.execute("""SELECT session_id,run_id,sequence_no,title,mentor_name,starts_at,ends_at,content_url,
          version,(archived_at IS NOT NULL) AS archived
          FROM richon.course_sessions
          WHERE run_id=%s AND (%s OR archived_at IS NULL)
          ORDER BY sequence_no,starts_at,session_id""",(run_id,include_archived))
        return _rows(cur)
