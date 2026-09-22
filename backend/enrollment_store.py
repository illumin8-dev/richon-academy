"""Unified read-only enrollment projection. No grant/payment/identity writes."""
from portal_store import read_cursor, _literal_search

# All selectable identifiers/orderings are constants, never request text.
ORDERING = {
    'ending': 'ends_before ASC NULLS LAST, full_name, enrollment_id',
    'newest': 'applied_at DESC, enrollment_id DESC',
    'name': 'full_name, enrollment_id',
}
CTE = """
WITH dated AS (
    SELECT r.*, %(as_of)s::date AS as_of,
        CASE WHEN cancelled_at IS NOT NULL THEN 'cancelled'
             WHEN total_months=0 THEN 'pending'
             WHEN calendar_review_required THEN 'needs_review'
             WHEN %(as_of)s::date < starts_on THEN 'scheduled'
             WHEN %(as_of)s::date >= ends_before THEN 'ended'
             ELSE 'active' END AS enrollment_status,
        ends_before - 1 AS ends_on,
        CASE WHEN ends_before IS NOT NULL THEN GREATEST(ends_before - %(as_of)s::date, 0) END AS remaining_days
    FROM richon.enrollment_read_model r
), filtered AS (
    SELECT d.* FROM dated d
    WHERE (%(member_id)s::uuid IS NULL OR d.member_id=%(member_id)s::uuid)
      AND (%(course_id)s::text IS NULL OR course_id=%(course_id)s)
      AND (%(cohort)s::text IS NULL OR cohort=%(cohort)s)
      AND (%(months)s::integer IS NULL OR latest_plan_months=%(months)s)
      AND (%(status)s::text IS NULL OR enrollment_status=%(status)s)
      AND (%(end_from)s::date IS NULL OR ends_on >= %(end_from)s::date)
      AND (%(end_to)s::date IS NULL OR ends_on <= %(end_to)s::date)
      AND (%(receipt)s::text IS NULL
           OR (%(receipt)s='requested' AND cash_receipt_requested IS TRUE)
           OR (%(receipt)s='not_requested' AND cash_receipt_requested IS FALSE)
           OR (%(receipt)s='unknown' AND cash_receipt_requested IS NULL))
      AND (%(q)s='' OR full_name ILIKE %(pattern)s ESCAPE E'\\\\'
           OR nickname ILIKE %(pattern)s ESCAPE E'\\\\'
           OR enrollment_id::text=%(q)s OR learner_id::text=%(q)s
           OR EXISTS (SELECT 1 FROM richon.learner_profiles p WHERE p.learner_id=d.learner_id
                      AND (lower(p.email)=lower(%(q)s) OR p.phone=%(phone_search)s)))
)
"""
FIELDS = """enrollment_id,learner_id,member_id,full_name,nickname,email_masked,phone_masked,
course_id,course_title,cohort,joined_at,applied_at,starts_on,ends_on,
remaining_days,enrollment_status,calendar_review_required,latest_plan_months,total_months,
confirmed_term_count,pending_term_count,latest_agreed_amount_krw,latest_discount_krw,
agreed_total_krw,cash_receipt_requested,latest_term_status,
NULL::bigint AS paid_amount_krw, 'not_connected'::text AS payment_status,
'unverified'::text AS cash_receipt_status"""


def rows(cur):
    names = [column.name for column in cur.description]
    return [dict(zip(names,row,strict=True)) for row in cur.fetchall()]


def overview(query, as_of, *, member_id=None):
    """One snapshot for page, counts and per-course distinct learners.

    `member_id=None` is admin-only; the HTTP route must enforce require_admin.
    The member route always supplies the session principal, never a request ID.
    """
    params = query.model_dump()
    params.update(as_of=as_of, member_id=member_id,
                  pattern=_literal_search(query.q),
                  phone_search=query.q.replace('-','').replace(' ',''))
    with read_cursor() as cur:
        cur.execute(CTE + """
            SELECT count(*) AS enrollment_count, count(DISTINCT learner_id) AS learner_count,
              count(DISTINCT learner_id) FILTER (WHERE enrollment_status='active') AS active_learners,
              count(*) FILTER (WHERE enrollment_status='scheduled') AS scheduled_enrollments,
              count(*) FILTER (WHERE enrollment_status='active' AND remaining_days BETWEEN 1 AND 7) AS ending_soon,
              count(*) FILTER (WHERE enrollment_status='pending') AS pending_enrollments,
              count(*) FILTER (WHERE enrollment_status='needs_review') AS needs_review
            FROM filtered
        """, params)
        summary = rows(cur)[0]
        cur.execute(CTE + 'SELECT ' + FIELDS + ' FROM filtered ORDER BY ' + ORDERING[query.sort] + ' LIMIT %(limit)s OFFSET %(offset)s', params)
        items = rows(cur)
        cur.execute(CTE + """
            SELECT course_id, course_title, cohort,
              count(DISTINCT learner_id) FILTER (WHERE enrollment_status='active') AS active_learners,
              count(*) FILTER (WHERE enrollment_status='scheduled') AS scheduled_enrollments,
              count(*) AS matching_enrollments
            FROM filtered GROUP BY course_id, course_title, cohort
            ORDER BY course_title,course_id LIMIT 101
        """, params)
        courses = rows(cur)
    return dict(items=items, summary=summary, courses=courses[:100],
                courses_truncated=len(courses)>100, as_of=as_of,
                limit=query.limit,offset=query.offset,
                has_more=query.offset+len(items)<summary['enrollment_count'])
