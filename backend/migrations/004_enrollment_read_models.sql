-- Staged/read-model preparation ONLY. No existing row is changed or inferred.
CREATE TABLE richon.course_schedules (
    course_id varchar(64) PRIMARY KEY REFERENCES richon.courses(course_id),
    starts_on date NOT NULL CHECK (starts_on BETWEEN DATE '2000-01-01' AND DATE '2100-12-31'),
    UNIQUE (course_id, starts_on)
);
CREATE TABLE richon.course_monthly_prices (
    course_id varchar(64) NOT NULL REFERENCES richon.courses(course_id),
    months integer NOT NULL CHECK (months IN (1,3,12)),
    list_amount_krw integer NOT NULL CHECK (list_amount_krw > 0),
    sale_amount_krw integer NOT NULL CHECK (sale_amount_krw > 0 AND sale_amount_krw <= list_amount_krw),
    enabled boolean NOT NULL DEFAULT FALSE,
    PRIMARY KEY (course_id, months)
);
-- Stable learner IDs support verified guests without treating contact equality
-- as identity. Linking a member is a future authorized/verified write flow.
CREATE TABLE richon.learner_profiles (
    learner_id uuid PRIMARY KEY,
    member_id uuid UNIQUE REFERENCES richon.members(member_id),
    full_name varchar(80) NOT NULL CHECK (length(btrim(full_name)) > 0),
    nickname varchar(80),
    email varchar(254),
    phone varchar(20) CHECK (phone IS NULL OR phone ~ '^01[0-9]{8,9}$'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE richon.course_enrollments (
    enrollment_id uuid PRIMARY KEY,
    learner_id uuid NOT NULL REFERENCES richon.learner_profiles(learner_id),
    course_id varchar(64) NOT NULL,
    starts_on date NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancelled_at timestamptz,
    FOREIGN KEY (course_id, starts_on) REFERENCES richon.course_schedules(course_id, starts_on),
    UNIQUE (learner_id, course_id)
);
-- Each confirmed purchase/extension is a separate immutable-history candidate.
-- The future write API must authorize confirmation; no such API exists here.
CREATE TABLE richon.enrollment_terms (
    term_id uuid PRIMARY KEY,
    enrollment_id uuid NOT NULL REFERENCES richon.course_enrollments(enrollment_id),
    sequence integer NOT NULL CHECK (sequence > 0),
    months integer NOT NULL CHECK (months IN (1,3,12)),
    list_amount_krw integer NOT NULL CHECK (list_amount_krw > 0),
    agreed_amount_krw integer NOT NULL CHECK (agreed_amount_krw > 0 AND agreed_amount_krw <= list_amount_krw),
    status varchar(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','cancelled')),
    cash_receipt_requested boolean,
    requested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at timestamptz,
    CHECK ((status='confirmed') = (confirmed_at IS NOT NULL)),
    UNIQUE (enrollment_id, sequence)
);
CREATE INDEX course_enrollments_course_idx ON richon.course_enrollments(course_id);
CREATE INDEX learner_profiles_member_idx ON richon.learner_profiles(member_id) WHERE member_id IS NOT NULL;

CREATE VIEW richon.enrollment_read_model AS
WITH totals AS (
    SELECT enrollment_id,
        COALESCE(sum(months) FILTER (WHERE status='confirmed'),0)::integer AS total_months,
        count(*) FILTER (WHERE status='confirmed')::integer AS confirmed_term_count,
        count(*) FILTER (WHERE status='pending')::integer AS pending_term_count,
        COALESCE(sum(agreed_amount_krw) FILTER (WHERE status='confirmed'),0)::bigint AS agreed_total_krw
    FROM richon.enrollment_terms GROUP BY enrollment_id
), base AS (
    SELECT e.enrollment_id, e.learner_id, l.member_id, e.course_id,
        c.title AS course_title, c.cohort, l.full_name, l.nickname,
        CASE WHEN l.email IS NULL THEN NULL ELSE left(split_part(l.email,'@',1),1) || '***@' || split_part(l.email,'@',2) END AS email_masked,
        CASE WHEN l.phone IS NULL THEN NULL ELSE left(l.phone,3) || '-****-' || right(l.phone,4) END AS phone_masked,
        m.created_at AS joined_at, e.applied_at, e.starts_on, e.cancelled_at,
        COALESCE(t.total_months,0) AS total_months,
        COALESCE(t.confirmed_term_count,0) AS confirmed_term_count,
        COALESCE(t.pending_term_count,0) AS pending_term_count,
        COALESCE(t.agreed_total_krw,0) AS agreed_total_krw,
        last_term.months AS latest_plan_months,
        last_term.agreed_amount_krw AS latest_agreed_amount_krw,
        last_term.list_amount_krw - last_term.agreed_amount_krw AS latest_discount_krw,
        last_term.cash_receipt_requested,
        last_term.status AS latest_term_status
    FROM richon.course_enrollments e
    JOIN richon.learner_profiles l ON l.learner_id=e.learner_id
    JOIN richon.courses c ON c.course_id=e.course_id
    LEFT JOIN richon.members m ON m.member_id=l.member_id
    LEFT JOIN totals t ON t.enrollment_id=e.enrollment_id
    LEFT JOIN LATERAL (
        SELECT months,agreed_amount_krw,list_amount_krw,cash_receipt_requested,status
        FROM richon.enrollment_terms WHERE enrollment_id=e.enrollment_id AND status<>'cancelled'
        ORDER BY sequence DESC LIMIT 1
    ) last_term ON TRUE
), calendar AS (
    SELECT *, CASE WHEN total_months BETWEEN 1 AND 1200
        THEN (starts_on + total_months * interval '1 month')::date END AS anniversary
    FROM base
)
SELECT enrollment_id,learner_id,member_id,course_id,course_title,cohort,
    full_name,nickname,email_masked,phone_masked,joined_at,applied_at,starts_on,cancelled_at,
    total_months,confirmed_term_count,pending_term_count,agreed_total_krw,
    latest_plan_months,latest_agreed_amount_krw,latest_discount_krw,cash_receipt_requested,latest_term_status,
    -- Ordinary anniversary boundary is exclusive: Oct 1 + 1 month -> Nov 1.
    -- Do not silently adopt PostgreSQL's month-end clamp before owner approval.
    CASE WHEN extract(day FROM anniversary)=extract(day FROM starts_on) THEN anniversary END AS ends_before,
    (total_months > 0 AND (anniversary IS NULL OR extract(day FROM anniversary)<>extract(day FROM starts_on))) AS calendar_review_required
FROM calendar;
REVOKE ALL ON richon.course_schedules,richon.course_monthly_prices,richon.learner_profiles,
    richon.course_enrollments,richon.enrollment_terms,richon.enrollment_read_model FROM PUBLIC;
