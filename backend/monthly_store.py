"""Monthly read models. No registrations, merging, payments or entitlement writes."""
from datetime import date
import re
from uuid import UUID
from portal_store import read_cursor, _literal_search


class MissingEnrollment(Exception):
    pass


def month_start(value: str) -> date:
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])',value):
        raise ValueError('invalid_month')
    return date.fromisoformat(value + '-01')


def add_months(start: date, months: int) -> date:
    if type(months) is not int or start.day!=1:
        raise ValueError('month_only_arithmetic')
    year, month = divmod(start.year*12 + start.month-1 + months,12)
    return date(year,month+1,1)


def _rows(cur):
    names = [x.name for x in cur.description]
    return [dict(zip(names,row,strict=True)) for row in cur.fetchall()]


BASE = r'''
WITH grouped AS (
 SELECT e.enrollment_id,e.learner_id,e.course_id,c.title AS course_title,c.cohort,
        l.name,l.nickname,l.member_id,m.created_at AS joined_at,r.start_month,r.duration_kind,
        CASE WHEN l.phone IS NULL THEN NULL ELSE left(l.phone,3)||'-****-'||right(l.phone,4) END AS phone_masked,
        CASE WHEN l.email IS NULL THEN NULL ELSE left(split_part(l.email,'@',1),1)||'***@'||split_part(l.email,'@',2) END AS email_masked,
        coalesce(sum(t.months) FILTER (WHERE t.grant_state='confirmed'),0)::integer AS confirmed_months,
        coalesce(max(t.months) FILTER (WHERE t.grant_state='pending'),0)::integer AS pending_max_months,
        count(t.term_id) FILTER (WHERE t.grant_state='pending')::integer AS pending_terms,
        count(t.term_id)::integer AS term_count,
        sum(t.paid_amount_krw - t.refunded_amount_krw) AS net_recorded_paid_krw,
        coalesce(sum(t.refunded_amount_krw),0) AS refunded_krw,
        max(t.applied_at) AS last_applied_at,
        (array_agg(t.months ORDER BY t.sequence_no DESC) FILTER (WHERE t.term_id IS NOT NULL))[1] AS last_plan_months,
        (array_agg(t.quoted_amount_krw ORDER BY t.sequence_no DESC) FILTER (WHERE t.term_id IS NOT NULL))[1] AS latest_quoted_krw,
        (array_agg(t.payment_state ORDER BY t.sequence_no DESC) FILTER (WHERE t.term_id IS NOT NULL))[1] AS latest_payment_state,
        (array_agg(t.receipt_state ORDER BY t.sequence_no DESC) FILTER (WHERE t.term_id IS NOT NULL))[1] AS latest_receipt_state
 FROM richon.monthly_enrollments e
 JOIN richon.course_month_rules r USING(course_id)
 JOIN richon.courses c USING(course_id)
 JOIN richon.enrollment_learners l USING(learner_id)
 LEFT JOIN richon.members m ON m.member_id=l.member_id
 LEFT JOIN richon.monthly_enrollment_terms t USING(enrollment_id)
 WHERE (%(course)s::text IS NULL OR e.course_id=%(course)s)
   /* manual_archive_filter */
   AND (l.name ILIKE %(like)s ESCAPE E'\\' OR coalesce(l.nickname,'') ILIKE %(like)s ESCAPE E'\\'
        OR l.phone=%(phone)s OR lower(l.email)=lower(%(q)s))
   AND (%(linked)s::boolean IS NULL OR (l.member_id IS NOT NULL)=%(linked)s)
   AND ((%(plan)s::integer IS NULL AND %(payment)s::text IS NULL AND %(receipt)s::text IS NULL)
        OR EXISTS (SELECT 1 FROM richon.monthly_enrollment_terms f WHERE f.enrollment_id=e.enrollment_id
             AND (%(plan)s::integer IS NULL OR f.months=%(plan)s)
             AND (%(payment)s::text IS NULL OR f.payment_state=%(payment)s)
             AND (%(receipt)s::text IS NULL OR f.receipt_state=%(receipt)s)))
 GROUP BY e.enrollment_id,e.learner_id,e.course_id,c.title,c.cohort,l.name,l.nickname,l.member_id,
          l.phone,l.email,m.created_at,r.start_month,r.duration_kind
), spans AS (
 SELECT *,CASE WHEN confirmed_months>0 THEN (start_month + (confirmed_months-1)*interval '1 month')::date END AS end_month,
        CASE WHEN duration_kind='fixed' AND confirmed_months+pending_max_months>0 THEN (start_month+interval '1 month')::date
             WHEN confirmed_months+pending_max_months>0
             THEN (start_month + (confirmed_months+pending_max_months-1)*interval '1 month')::date END AS proposed_end
 FROM grouped
), statuses AS (
 SELECT *,CASE WHEN confirmed_months=0 THEN 'pending'
               WHEN %(month)s::date<start_month THEN 'scheduled'
               WHEN %(month)s::date<=end_month THEN 'active'
               ELSE 'ended' END AS status
 FROM spans
), filtered AS (
 SELECT * FROM statuses
 WHERE (%(scope)s='all' OR (%(month)s::date>=start_month AND %(month)s::date<=coalesce(proposed_end,end_month)))
   AND (%(state)s::text IS NULL OR status=%(state)s OR (%(state)s='ending' AND end_month=%(month)s::date))
   AND (%(end_from)s::date IS NULL OR end_month>=%(end_from)s)
   AND (%(end_to)s::date IS NULL OR end_month<=%(end_to)s)
)
'''
ROW_FIELDS = '''enrollment_id,learner_id,course_id,course_title,cohort,name,nickname,
    phone_masked,email_masked,(member_id IS NOT NULL) AS member_linked,joined_at,
    to_char(start_month,'YYYY-MM') AS start_month,to_char(end_month,'YYYY-MM') AS end_month,
    duration_kind,confirmed_months,pending_terms,term_count,status,last_plan_months,
    last_applied_at,latest_quoted_krw,net_recorded_paid_krw,refunded_krw,
    latest_payment_state,latest_receipt_state'''


def _base_for_schema(cur):
    """Honor persisted archives independently of the manual-write feature flag.

    Migration 004 remains readable before optional migration 005 is applied.
    After 005 is recorded, a missing archive table is an error, not permission
    to silently count archived records again. Do not catch DB access failures.
    This check and all three reads share read_cursor's repeatable-read snapshot.
    """
    cur.execute("""SELECT to_regclass('richon.manual_enrollments') IS NOT NULL,
        EXISTS (SELECT 1 FROM richon.schema_migrations
                WHERE version='005_manual_registry')""")
    archive_exists, migration_applied = cur.fetchone()
    if not archive_exists and migration_applied:
        raise RuntimeError('manual_archive_store_unavailable')
    # Only fixed SQL is selected here; every search value remains a bind value.
    clause = """AND NOT EXISTS (
        SELECT 1 FROM richon.manual_enrollments archive
        WHERE archive.enrollment_id=e.enrollment_id AND archive.archived_at IS NOT NULL
    )""" if archive_exists else ''
    return BASE.replace('/* manual_archive_filter */', clause)


def search(filters):
    f = filters.model_dump()
    p = {
        'month': month_start(f['month']), 'scope':f['scope'], 'course':f['course_id'],
        'q':f['q'], 'like':_literal_search(f['q']),
        'phone':re.sub(r'[ ()-]','',f['q']),
        'linked':f['member_linked'], 'plan':f['plan_months'], 'payment':f['payment_state'],
        'receipt':f['receipt_state'],'state':f['status'],
        'end_from':month_start(f['end_from']) if f['end_from'] else None,
        'end_to':month_start(f['end_to']) if f['end_to'] else None,
        'limit':f['limit'],'offset':f['offset'],
    }
    if p['phone'].startswith('+82'): p['phone']='0'+p['phone'][3:]
    with read_cursor() as cur:
        base = _base_for_schema(cur)
        cur.execute(base+'''SELECT count(*)::integer AS total,
          count(DISTINCT learner_id) FILTER (WHERE %(month)s::date BETWEEN start_month AND end_month)::integer AS confirmed_people,
          count(*) FILTER (WHERE %(month)s::date BETWEEN start_month AND end_month)::integer AS confirmed_enrollments,
          count(DISTINCT learner_id) FILTER (WHERE start_month=%(month)s::date AND confirmed_months>0)::integer AS starting_people,
          count(DISTINCT learner_id) FILTER (WHERE end_month=%(month)s::date)::integer AS ending_people,
          count(DISTINCT learner_id) FILTER (WHERE pending_terms>0 AND %(month)s::date BETWEEN start_month AND proposed_end)::integer AS pending_people
          FROM filtered''',p)
        summary = _rows(cur)[0]
        cur.execute(base+'''SELECT course_id,course_title,cohort,
          count(DISTINCT learner_id) FILTER (WHERE %(month)s::date BETWEEN start_month AND end_month)::integer AS confirmed_people,
          count(DISTINCT learner_id) FILTER (WHERE pending_terms>0 AND %(month)s::date BETWEEN start_month AND proposed_end)::integer AS pending_people
          FROM filtered GROUP BY course_id,course_title,cohort ORDER BY course_title,cohort NULLS LAST,course_id LIMIT 201''',p)
        course_summary = _rows(cur)
        cur.execute(base+'SELECT '+ROW_FIELDS+''' FROM filtered
          ORDER BY end_month ASC NULLS LAST,name,enrollment_id LIMIT %(limit)s OFFSET %(offset)s''',p)
        items = _rows(cur)
    return {'month':f['month'],'summary':summary,'courses':course_summary[:200],
            'courses_truncated':len(course_summary)>200,'items':items,'limit':f['limit'],
            'offset':f['offset'],'has_more':f['offset']+len(items)<summary['total']}


def options():
    with read_cursor() as cur:
        cur.execute('''SELECT c.course_id,c.title,c.cohort,to_char(r.start_month,'YYYY-MM') AS start_month,
               r.duration_kind,r.fixed_months FROM richon.course_month_rules r
               JOIN richon.courses c USING(course_id) ORDER BY c.title,c.cohort NULLS LAST,c.course_id LIMIT 201''')
        rows = _rows(cur)
    return {'items':rows[:200],'has_more':len(rows)>200}


def history(enrollment_id: UUID, limit: int, offset: int):
    with read_cursor() as cur:
        cur.execute('SELECT 1 FROM richon.monthly_enrollments WHERE enrollment_id=%s',(enrollment_id,))
        if cur.fetchone() is None: raise MissingEnrollment()
        cur.execute('''WITH terms AS (
            SELECT t.*,r.start_month,
                   coalesce(sum(t.months) FILTER (WHERE t.grant_state='confirmed') OVER
                     (ORDER BY t.sequence_no ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0) AS preceding_months
            FROM richon.monthly_enrollment_terms t JOIN richon.monthly_enrollments e USING(enrollment_id)
            JOIN richon.course_month_rules r USING(course_id) WHERE t.enrollment_id=%s
        ) SELECT term_id,sequence_no,months,grant_state,order_id,applied_at,
          CASE WHEN grant_state='confirmed' THEN to_char(start_month+preceding_months*interval '1 month','YYYY-MM') END AS start_month,
          CASE WHEN grant_state='confirmed' THEN to_char(start_month+(preceding_months+months-1)*interval '1 month','YYYY-MM') END AS end_month,
          quoted_amount_krw,payment_state,paid_amount_krw,refunded_amount_krw,paid_at,receipt_state
          FROM terms ORDER BY sequence_no DESC LIMIT %s OFFSET %s''',(enrollment_id,limit+1,offset))
        rows = _rows(cur)
    return {'items':rows[:limit],'limit':limit,'offset':offset,'has_more':len(rows)>limit}
