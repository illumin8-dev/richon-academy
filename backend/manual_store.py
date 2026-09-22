"""Manual legacy records only. Never creates members, PG transactions or OAuth links."""
import hashlib
import json
import re
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
import auth_core
from portal_store import _literal_search
from monthly_store import _rows, month_start

class Rejected(Exception):
    def __init__(self, code='record_conflict', status=409):
        self.code, self.status = code, status
        super().__init__(code)

@contextmanager
def transaction(actor):
    with auth_core._transaction() as cur:
        cur.execute('SELECT role,status FROM richon.members WHERE member_id=%s FOR SHARE',(actor,))
        if cur.fetchone() != ('admin','active'): raise Rejected('admin_required',403)
        yield cur


def audit(cur, actor, operation, entity, reason, result, request_id=None, fingerprint=None):
    cur.execute('''INSERT INTO richon.manual_audit
       (event_id,actor_id,request_id,fingerprint,operation,entity_id,reason,result)
       VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)''',
       (uuid4(),actor,request_id,fingerprint,operation,str(entity),reason,json.dumps(result)))


def mutate(actor, operation, payload):
    """Same actor/key/body retries return the committed result; changed bodies conflict."""
    data=payload.model_dump()
    fingerprint=hashlib.sha256(json.dumps([operation,data],sort_keys=True,ensure_ascii=True).encode()).hexdigest()
    key=int.from_bytes(hashlib.sha256((str(actor)+data['request_id']).encode()).digest()[:8],'big',signed=True)
    try:
        with transaction(actor) as cur:
            cur.execute('SELECT pg_advisory_xact_lock(%s)',(key,))
            cur.execute('SELECT fingerprint,result FROM richon.manual_audit WHERE actor_id=%s AND request_id=%s',
                        (actor,data['request_id']))
            prior=cur.fetchone()
            if prior:
                if prior[0] != fingerprint: raise Rejected('request_key_reused')
                result=prior[1]
            else:
                handler={'create':create,'profile':update_profile,'term.add':add_term,
                         'term.edit':edit_term,'archive':archive,'course.create':create_course}[operation]
                result=handler(cur,actor,payload)
                audit(cur,actor,operation,result.get('enrollment_id',result.get('course_id','')),
                      payload.reason,result,payload.request_id,fingerprint)
    except Rejected: raise
    except Exception as exc:
        if getattr(exc,'sqlstate',None) in {'23505','23503','23514','P0001','40001','40P01'}:
            raise Rejected('record_conflict') from None
        raise
    return result  # Only after transaction COMMIT succeeds.


def _learner(cur, learner_id, version=None):
    cur.execute('''SELECT x.version,l.member_id FROM richon.manual_learners x
       JOIN richon.enrollment_learners l USING(learner_id) WHERE learner_id=%s FOR UPDATE OF x,l''',(learner_id,))
    row=cur.fetchone()
    if row is None: raise Rejected('manual_learner_not_found',404)
    if row[1] is not None: raise Rejected('linked_member_requires_separate_workflow')
    if version is not None and version != row[0]: raise Rejected('stale_record')
    return row[0]


def _enrollment(cur, enrollment_id, version, allow_archived=False):
    cur.execute('''SELECT x.version,x.archived_at,e.learner_id,e.course_id,r.duration_kind
      FROM richon.manual_enrollments x JOIN richon.monthly_enrollments e USING(enrollment_id)
      JOIN richon.course_month_rules r USING(course_id) WHERE enrollment_id=%s FOR UPDATE OF x,e''',(enrollment_id,))
    row=cur.fetchone()
    if row is None: raise Rejected('manual_enrollment_not_found',404)
    if row[0] != version: raise Rejected('stale_record')
    if row[1] and not allow_archived: raise Rejected('archived_record')
    return row


def _bump(cur, enrollment_id):
    cur.execute('''UPDATE richon.manual_enrollments SET version=version+1,updated_at=CURRENT_TIMESTAMP
                   WHERE enrollment_id=%s RETURNING version''',(enrollment_id,))
    return cur.fetchone()[0]


def _day(value):
    if not value: return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone(timedelta(hours=9)))


def _insert_term(cur, actor, eid, term, request_id):
    cur.execute('''SELECT r.duration_kind FROM richon.monthly_enrollments e
                 JOIN richon.course_month_rules r USING(course_id) WHERE enrollment_id=%s''',(eid,))
    kind=cur.fetchone()[0]
    cur.execute("SELECT count(*),coalesce(max(sequence_no),0),count(*) FILTER(WHERE grant_state='pending') FROM richon.monthly_enrollment_terms WHERE enrollment_id=%s",(eid,))
    count,sequence,pending=cur.fetchone()
    if pending: raise Rejected('pending_term_exists')
    if kind=='fixed' and count: raise Rejected('fixed_course_cannot_extend')
    if (kind=='monthly' and term.months not in (1,3,12)) or (kind=='fixed' and term.months!=2):
        raise Rejected('invalid_course_duration',422)
    tid=uuid4()
    cur.execute('''INSERT INTO richon.monthly_enrollment_terms
      (term_id,enrollment_id,sequence_no,months,grant_state,confirmed_at,confirmation_ref,
       quoted_amount_krw,payment_state,paid_amount_krw,paid_at,payment_record_ref,
       receipt_state,receipt_record_ref,applied_at)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
      (tid,eid,sequence+1,term.months,'confirmed' if term.confirmed else 'pending',
       datetime.now(timezone.utc) if term.confirmed else None,'manual:'+request_id if term.confirmed else None,
       term.quoted_amount_krw,term.payment_state,term.paid_amount_krw,_day(term.paid_on),term.payment_ref,
       term.receipt_state,term.receipt_ref,_day(term.applied_on)))
    cur.execute('INSERT INTO richon.manual_terms(term_id,created_by) VALUES(%s,%s)',(tid,actor))
    return str(tid)


def create(cur, actor, body):
    cur.execute('SELECT 1 FROM richon.course_month_rules WHERE course_id=%s FOR SHARE',(body.course_id,))
    if not cur.fetchone(): raise Rejected('course_not_found',404)
    if body.existing_learner_id:
        lid=UUID(body.existing_learner_id)
        _learner(cur,lid,body.learner_version)
    else:
        lid=uuid4();p=body.profile
        cur.execute('''INSERT INTO richon.enrollment_learners(learner_id,name,nickname,email,phone)
                       VALUES(%s,%s,%s,%s,%s)''',(lid,p.name,p.nickname,p.email,p.phone))
        cur.execute('''INSERT INTO richon.manual_learners(learner_id,original_joined_on,created_by)
                       VALUES(%s,%s,%s)''',(lid,p.original_joined_on,actor))
    eid=uuid4()
    cur.execute('INSERT INTO richon.monthly_enrollments(enrollment_id,learner_id,course_id) VALUES(%s,%s,%s)',(eid,lid,body.course_id))
    cur.execute('INSERT INTO richon.manual_enrollments(enrollment_id,created_by) VALUES(%s,%s)',(eid,actor))
    tid=_insert_term(cur,actor,eid,body.term,body.request_id)
    return {'enrollment_id':str(eid),'learner_id':str(lid),'term_id':tid,'version':1,'source':'manual'}


def update_profile(cur, actor, body):
    cur.execute('SELECT learner_id FROM richon.monthly_enrollments WHERE enrollment_id=%s',(body.enrollment_id,))
    row=cur.fetchone()
    if not row: raise Rejected('manual_enrollment_not_found',404)
    lid=row[0];_learner(cur,lid,body.learner_version)
    _enrollment(cur,body.enrollment_id,body.version)
    p=body.profile
    cur.execute('UPDATE richon.enrollment_learners SET name=%s,nickname=%s,email=%s,phone=%s WHERE learner_id=%s',
                (p.name,p.nickname,p.email,p.phone,lid))
    cur.execute('''UPDATE richon.manual_learners SET original_joined_on=%s,version=version+1,
                 updated_at=CURRENT_TIMESTAMP WHERE learner_id=%s RETURNING version''',(p.original_joined_on,lid))
    lv=cur.fetchone()[0]
    return {'enrollment_id':body.enrollment_id,'version':_bump(cur,body.enrollment_id),'learner_version':lv}


def add_term(cur, actor, body):
    _enrollment(cur,body.enrollment_id,body.version)
    tid=_insert_term(cur,actor,body.enrollment_id,body.term,body.request_id)
    return {'enrollment_id':body.enrollment_id,'term_id':tid,'version':_bump(cur,body.enrollment_id)}


def edit_term(cur, actor, body):
    row=_enrollment(cur,body.enrollment_id,body.version)
    cur.execute('''SELECT t.grant_state,t.order_id FROM richon.monthly_enrollment_terms t
         JOIN richon.manual_terms x USING(term_id) WHERE t.term_id=%s AND t.enrollment_id=%s FOR UPDATE OF t''',
         (body.term_id,body.enrollment_id))
    old=cur.fetchone()
    if not old: raise Rejected('manual_term_not_found',404)
    if old!=('pending',None): raise Rejected('confirmed_history_is_read_only')
    t=body.term
    if (row[4]=='monthly' and t.months not in (1,3,12)) or (row[4]=='fixed' and t.months!=2):
        raise Rejected('invalid_course_duration',422)
    cur.execute('''UPDATE richon.monthly_enrollment_terms SET months=%s,grant_state=%s,confirmed_at=%s,
        confirmation_ref=%s,quoted_amount_krw=%s,payment_state=%s,paid_amount_krw=%s,paid_at=%s,payment_record_ref=%s,
        receipt_state=%s,receipt_record_ref=%s,applied_at=%s WHERE term_id=%s''',
        (t.months,'confirmed' if t.confirmed else 'pending',datetime.now(timezone.utc) if t.confirmed else None,
         'manual:'+body.request_id if t.confirmed else None,t.quoted_amount_krw,t.payment_state,t.paid_amount_krw,
         _day(t.paid_on),t.payment_ref,t.receipt_state,t.receipt_ref,_day(t.applied_on),body.term_id))
    return {'enrollment_id':body.enrollment_id,'version':_bump(cur,body.enrollment_id),'term_id':body.term_id}


def archive(cur, actor, body):
    _enrollment(cur,body.enrollment_id,body.version,allow_archived=True)
    cur.execute('UPDATE richon.manual_enrollments SET archived_at=%s WHERE enrollment_id=%s',
                (datetime.now(timezone.utc) if body.archived else None,body.enrollment_id))
    return {'enrollment_id':body.enrollment_id,'version':_bump(cur,body.enrollment_id),'archived':body.archived}


def create_course(cur, actor, body):
    cid='manual-'+uuid4().hex
    cur.execute('''INSERT INTO richon.courses(course_id,title,cohort,price_krw,enabled)
                 VALUES(%s,%s,%s,%s,FALSE)''',(cid,body.title,body.cohort,body.price_krw))
    cur.execute('INSERT INTO richon.course_month_rules(course_id,start_month,duration_kind,fixed_months) VALUES(%s,%s,%s,%s)',
                (cid,month_start(body.start_month),body.duration_kind,2 if body.duration_kind=='fixed' else None))
    return {'course_id':cid,'enabled':False,'source':'manual'}


def detail(actor, eid):
    with transaction(actor) as cur:
        cur.execute('''SELECT e.enrollment_id,e.learner_id,e.course_id,x.version,(x.archived_at IS NOT NULL) AS archived,
             l.name,l.nickname,l.email,l.phone,y.version AS learner_version,y.original_joined_on,
             c.title,c.cohort,to_char(r.start_month,'YYYY-MM') AS start_month,r.duration_kind
             FROM richon.manual_enrollments x JOIN richon.monthly_enrollments e USING(enrollment_id)
             JOIN richon.manual_learners y USING(learner_id) JOIN richon.enrollment_learners l USING(learner_id)
             JOIN richon.courses c USING(course_id) JOIN richon.course_month_rules r USING(course_id)
             WHERE enrollment_id=%s''',(eid,))
        rows=_rows(cur)
        if not rows: raise Rejected('manual_enrollment_not_found',404)
        result=rows[0]
        cur.execute('''SELECT t.term_id,t.sequence_no,t.months,t.grant_state,t.quoted_amount_krw,
            t.payment_state,t.paid_amount_krw,to_char(t.paid_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD') AS paid_on,
            t.payment_record_ref AS payment_ref,t.receipt_state,t.receipt_record_ref AS receipt_ref,
            to_char(t.applied_at AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD') AS applied_on
            FROM richon.monthly_enrollment_terms t JOIN richon.manual_terms x USING(term_id)
            WHERE enrollment_id=%s ORDER BY sequence_no LIMIT 1000''',(eid,))
        result['terms']=_rows(cur)
        audit(cur,actor,'detail.read',eid,'manual_detail_view',{'fields':['name','nickname','email','phone','original_joined_on']})
    return result


def search(actor, body):
    phone=re.sub(r'[ ()-]','',body.q)
    if phone.startswith('+82'): phone='0'+phone[3:]
    with transaction(actor) as cur:
        cur.execute('''WITH records AS (
         SELECT e.enrollment_id,e.learner_id,e.course_id,x.version,(x.archived_at IS NOT NULL) AS archived,
           l.name,l.nickname,y.version AS learner_version,y.original_joined_on,c.title,c.cohort,
           to_char(r.start_month,'YYYY-MM') AS start_month,r.duration_kind,
           CASE WHEN t.months>0 THEN to_char(r.start_month+(t.months-1)*interval '1 month','YYYY-MM') END AS end_month,
           t.months AS confirmed_months,t.pending_terms,
           CASE WHEN l.phone IS NOT NULL THEN left(l.phone,3)||'-****-'||right(l.phone,4) END AS phone_masked,
           CASE WHEN l.email IS NOT NULL THEN left(split_part(l.email,'@',1),1)||'***@'||split_part(l.email,'@',2) END AS email_masked,
           x.created_at
         FROM richon.manual_enrollments x JOIN richon.monthly_enrollments e USING(enrollment_id)
         JOIN richon.enrollment_learners l USING(learner_id) JOIN richon.manual_learners y USING(learner_id)
         JOIN richon.courses c USING(course_id) JOIN richon.course_month_rules r USING(course_id)
         CROSS JOIN LATERAL(SELECT coalesce(sum(months) FILTER(WHERE grant_state='confirmed'),0)::integer AS months,
                 count(*) FILTER(WHERE grant_state='pending')::integer AS pending_terms
                 FROM richon.monthly_enrollment_terms WHERE enrollment_id=e.enrollment_id) t
         WHERE (x.archived_at IS NOT NULL)=%(archived)s
           AND (%(course)s::text IS NULL OR e.course_id=%(course)s)
           AND (l.name ILIKE %(q)s ESCAPE E'\\\\' OR coalesce(l.nickname,'') ILIKE %(q)s ESCAPE E'\\\\'
               OR l.phone=%(phone)s OR lower(l.email)=lower(%(exact)s))
        ) SELECT * FROM records
        WHERE (%(month)s::text IS NULL OR %(month)s BETWEEN start_month AND end_month)
        ORDER BY created_at DESC,enrollment_id DESC LIMIT %(limit)s OFFSET %(offset)s''',
        {'archived':body.archived,'course':body.course_id,'q':_literal_search(body.q),'exact':body.q,'phone':phone,
         'month':body.month,'limit':body.limit+1,'offset':body.offset})
        rows=_rows(cur)
    return {'items':rows[:body.limit],'has_more':len(rows)>body.limit,'offset':body.offset,'limit':body.limit}
