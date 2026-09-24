"""Bounded, read-only portal queries. Session touch is owned by auth_core.

No identity inference, order claiming, membership edits, or payment side effects.
"""
from contextlib import contextmanager
from uuid import UUID

import db
import member_profile


class MissingMember(Exception):
    pass


@contextmanager
def read_cursor():
    with db._connect(db.database_url()) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute("SET LOCAL lock_timeout = '3s'")
            yield cur


def _row(cur):
    row = cur.fetchone()
    if row is None:
        raise MissingMember()
    return dict(zip([c.name for c in cur.description], row, strict=True))


def _page(cur, limit: int, offset: int):
    names = [c.name for c in cur.description]
    rows = cur.fetchmany(limit + 1)
    return {
        "items": [dict(zip(names, row, strict=True)) for row in rows[:limit]],
        "limit": limit, "offset": offset, "has_more": len(rows) > limit,
    }


def _literal_search(q: str) -> str:
    # LIKE wildcards are data, not operators, for the search field.
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def profile(member_id: UUID):
    with read_cursor() as cur:
        cur.execute("""
            SELECT m.member_id, m.display_name, m.role, m.created_at,
                ARRAY(SELECT DISTINCT i.provider FROM richon.auth_identities i
                      WHERE i.member_id=m.member_id ORDER BY i.provider) AS providers,
                (SELECT count(*) FROM richon.member_order_links l
                 WHERE l.member_id=m.member_id) AS linked_order_count
            FROM richon.members m WHERE m.member_id=%s AND m.status='active'
        """, (member_id,))
        result = _row(cur)
        if member_profile.enabled():
            cur.execute('SELECT name,phone,email,age_range,gender,consultation_consent,consented_at FROM richon.member_profiles WHERE member_id=%s AND terms_version=%s AND privacy_version=%s AND over14_confirmed', (member_id, member_profile.VERSION, member_profile.VERSION))
            registration = _row(cur)
            result['display_name'] = registration['name']
            result['registration'] = registration
        return result


ORDER_FIELDS = "o.order_id, o.course_id, o.course_title, o.cohort, o.amount_krw, o.currency, o.status, o.created_at"


def own_orders(member_id: UUID, limit: int, offset: int):
    with read_cursor() as cur:
        cur.execute(f"""
            SELECT {ORDER_FIELDS}
            FROM richon.orders o JOIN richon.member_order_links l ON l.order_id=o.order_id
            WHERE l.member_id=%s
            ORDER BY o.created_at DESC, o.order_id DESC LIMIT %s OFFSET %s
        """, (member_id, limit + 1, offset))
        return _page(cur, limit, offset)


def summary():
    with read_cursor() as cur:
        cur.execute("""
            SELECT (SELECT count(*) FROM richon.members) AS members_total,
                (SELECT count(*) FROM richon.members WHERE status='active') AS members_active,
                (SELECT count(*) FROM richon.courses) AS courses_total,
                (SELECT count(*) FROM richon.courses WHERE enabled) AS courses_enabled,
                (SELECT count(*) FROM richon.orders) AS orders_total,
                (SELECT count(*) FROM richon.orders WHERE status='pending_payment') AS pending_orders,
                (SELECT count(*) FROM richon.orders o WHERE NOT EXISTS
                    (SELECT 1 FROM richon.member_order_links l WHERE l.order_id=o.order_id)) AS unlinked_orders
        """)
        return _row(cur)


def members(limit: int, offset: int, q: str, status: str | None):
    with read_cursor() as cur:
        cur.execute("""
            SELECT m.member_id, m.display_name, m.role, m.status, m.created_at,
                ARRAY(SELECT DISTINCT i.provider FROM richon.auth_identities i
                      WHERE i.member_id=m.member_id ORDER BY i.provider) AS providers,
                (SELECT count(*) FROM richon.member_order_links l
                 WHERE l.member_id=m.member_id) AS linked_order_count
            FROM richon.members m
            WHERE (m.display_name ILIKE %s ESCAPE E'\\\\' OR m.member_id::text=%s)
              AND (%s::text IS NULL OR m.status=%s)
            ORDER BY m.created_at DESC, m.member_id DESC LIMIT %s OFFSET %s
        """, (_literal_search(q), q, status, status, limit + 1, offset))
        return _page(cur, limit, offset)


def courses(limit: int, offset: int, q: str, enabled: bool | None):
    with read_cursor() as cur:
        cur.execute("""
            SELECT c.course_id, c.title, c.cohort, c.price_krw, c.enabled, c.created_at
            FROM richon.courses c
            WHERE (c.title ILIKE %s ESCAPE E'\\\\' OR c.cohort ILIKE %s ESCAPE E'\\\\' OR c.course_id=%s)
              AND (%s::boolean IS NULL OR c.enabled=%s)
            ORDER BY c.created_at DESC, c.course_id DESC LIMIT %s OFFSET %s
        """, (_literal_search(q), _literal_search(q), q, enabled, enabled, limit + 1, offset))
        return _page(cur, limit, offset)


def orders(limit: int, offset: int, q: str, linked: bool | None):
    with read_cursor() as cur:
        # Full contact details never leave the database in this list API.
        # Member contacts are not inferred from an unlinked order or profile.
        cur.execute(f"""
            SELECT {ORDER_FIELDS}, o.customer_name,
                left(o.customer_phone, 3) || '-****-' || right(o.customer_phone, 4) AS phone_masked,
                left(split_part(o.customer_email, '@', 1), 1) || '***@' ||
                split_part(o.customer_email, '@', 2) AS email_masked,
                (l.member_id IS NOT NULL) AS member_linked
            FROM richon.orders o LEFT JOIN richon.member_order_links l ON l.order_id=o.order_id
            WHERE (o.customer_name ILIKE %s ESCAPE E'\\\\' OR o.order_id=%s
                   OR o.customer_phone=%s OR lower(o.customer_email)=lower(%s))
              AND (%s::boolean IS NULL OR (l.member_id IS NOT NULL)=%s)
            ORDER BY o.created_at DESC, o.order_id DESC LIMIT %s OFFSET %s
        """, (_literal_search(q), q, q, q, linked, linked, limit + 1, offset))
        return _page(cur, limit, offset)
