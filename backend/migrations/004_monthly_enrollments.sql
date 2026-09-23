-- Review/CI only. No seeds, automatic payments, legacy claiming or startup DDL.
-- First-of-month dates below represent MONTHS, not time-of-day access expiry.
CREATE TABLE richon.course_month_rules (
    course_id varchar(64) PRIMARY KEY REFERENCES richon.courses(course_id),
    start_month date NOT NULL CHECK (isfinite(start_month) AND extract(day FROM start_month)=1),
    duration_kind varchar(12) NOT NULL CHECK (duration_kind IN ('monthly','fixed')),
    fixed_months integer,
    CHECK ((duration_kind='monthly' AND fixed_months IS NULL) OR (duration_kind='fixed' AND fixed_months IS NOT NULL AND fixed_months=2))
);
CREATE TABLE richon.enrollment_learners (
    learner_id uuid PRIMARY KEY,
    member_id uuid UNIQUE REFERENCES richon.members(member_id),
    name varchar(80) NOT NULL CHECK (length(btrim(name))>0),
    nickname varchar(80), email varchar(254),
    phone varchar(16) CHECK (phone IS NULL OR phone ~ '^01[0-9]{8,9}$'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE richon.monthly_enrollments (
    enrollment_id uuid PRIMARY KEY,
    learner_id uuid NOT NULL REFERENCES richon.enrollment_learners(learner_id),
    course_id varchar(64) NOT NULL REFERENCES richon.course_month_rules(course_id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (learner_id,course_id)
);
CREATE TABLE richon.monthly_enrollment_terms (
    term_id uuid PRIMARY KEY,
    enrollment_id uuid NOT NULL REFERENCES richon.monthly_enrollments(enrollment_id),
    sequence_no integer NOT NULL CHECK (sequence_no BETWEEN 1 AND 1000),
    months integer NOT NULL CHECK (months IN (1,2,3,12)),
    grant_state varchar(12) NOT NULL DEFAULT 'pending' CHECK (grant_state IN ('pending','confirmed','cancelled')),
    confirmed_at timestamptz, confirmation_ref varchar(200),
    order_id varchar(64) UNIQUE REFERENCES richon.orders(order_id),
    quoted_amount_krw integer CHECK (quoted_amount_krw BETWEEN 0 AND 100000000),
    payment_state varchar(16) NOT NULL DEFAULT 'unknown' CHECK (payment_state IN ('unknown','pending','recorded','refunded')),
    paid_amount_krw integer CHECK (paid_amount_krw BETWEEN 0 AND 100000000),
    refunded_amount_krw integer NOT NULL DEFAULT 0 CHECK (refunded_amount_krw>=0),
    paid_at timestamptz, payment_record_ref varchar(200),
    receipt_state varchar(20) NOT NULL DEFAULT 'unknown' CHECK (receipt_state IN ('unknown','not_requested','requested','recorded_issued')),
    receipt_record_ref varchar(200),
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (enrollment_id,sequence_no),
    CHECK (grant_state<>'confirmed' OR
      (confirmed_at IS NOT NULL AND confirmation_ref IS NOT NULL AND length(btrim(confirmation_ref))>0
       AND payment_state NOT IN ('pending','refunded'))),
    CHECK ((payment_state IN ('unknown','pending') AND paid_amount_krw IS NULL AND paid_at IS NULL AND refunded_amount_krw=0)
      OR (payment_state IN ('recorded','refunded') AND paid_amount_krw IS NOT NULL AND paid_at IS NOT NULL
          AND payment_record_ref IS NOT NULL AND length(btrim(payment_record_ref))>0 AND refunded_amount_krw<=paid_amount_krw)),
    CHECK (payment_state<>'refunded' OR refunded_amount_krw>0),
    CHECK (receipt_state<>'recorded_issued' OR (receipt_record_ref IS NOT NULL AND length(btrim(receipt_record_ref))>0))
);
CREATE INDEX monthly_enrollments_course_idx ON richon.monthly_enrollments(course_id);
CREATE INDEX monthly_terms_state_idx ON richon.monthly_enrollment_terms(enrollment_id,grant_state);
CREATE FUNCTION richon.validate_monthly_term() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rule_kind text; fixed integer; course text; learner_member uuid; owner_member uuid;
        order_course text; order_amount integer;
BEGIN
    IF TG_OP='DELETE' THEN
        IF OLD.grant_state='confirmed' THEN RAISE EXCEPTION 'confirmed_grant_immutable'; END IF;
        RETURN OLD;
    END IF;
    IF TG_OP='UPDATE' THEN
        IF NEW.enrollment_id<>OLD.enrollment_id OR NEW.sequence_no<>OLD.sequence_no THEN
            RAISE EXCEPTION 'term_identity_immutable';
        END IF;
        IF OLD.grant_state='confirmed' AND (NEW.grant_state<>OLD.grant_state OR NEW.months<>OLD.months) THEN
            RAISE EXCEPTION 'confirmed_grant_immutable';
        END IF;
    END IF;
    SELECT e.course_id,l.member_id INTO course,learner_member
      FROM richon.monthly_enrollments e JOIN richon.enrollment_learners l USING(learner_id)
      WHERE e.enrollment_id=NEW.enrollment_id FOR UPDATE OF e;
    SELECT duration_kind,fixed_months INTO rule_kind,fixed FROM richon.course_month_rules WHERE course_id=course FOR SHARE;
    IF rule_kind IS NULL OR (rule_kind='monthly' AND NEW.months NOT IN (1,3,12)) OR (rule_kind='fixed' AND NEW.months<>fixed) THEN
        RAISE EXCEPTION 'invalid_course_duration';
    END IF;
    IF NEW.grant_state='confirmed' THEN
        IF EXISTS (SELECT 1 FROM richon.monthly_enrollment_terms WHERE enrollment_id=NEW.enrollment_id
                    AND term_id<>NEW.term_id AND grant_state='confirmed'
                    AND (rule_kind='fixed' OR sequence_no>NEW.sequence_no)) THEN
            RAISE EXCEPTION 'invalid_grant_sequence';
        END IF;
    END IF;
    IF NEW.order_id IS NOT NULL THEN
        SELECT course_id,amount_krw INTO order_course,order_amount FROM richon.orders WHERE order_id=NEW.order_id;
        IF order_course IS DISTINCT FROM course OR order_amount IS DISTINCT FROM NEW.quoted_amount_krw THEN
            RAISE EXCEPTION 'order_snapshot_mismatch';
        END IF;
        SELECT member_id INTO owner_member FROM richon.member_order_links WHERE order_id=NEW.order_id;
        IF owner_member IS NOT NULL AND owner_member IS DISTINCT FROM learner_member THEN RAISE EXCEPTION 'order_owner_mismatch'; END IF;
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER monthly_term_guard BEFORE INSERT OR UPDATE OR DELETE ON richon.monthly_enrollment_terms
    FOR EACH ROW EXECUTE FUNCTION richon.validate_monthly_term();
-- Preserve historical month boundaries. Editing an offering after enrollment is a separate future workflow.
CREATE FUNCTION richon.freeze_monthly_course_rule() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.start_month,NEW.duration_kind,NEW.fixed_months) IS DISTINCT FROM (OLD.start_month,OLD.duration_kind,OLD.fixed_months)
       AND EXISTS(SELECT 1 FROM richon.monthly_enrollments WHERE course_id=OLD.course_id) THEN
        RAISE EXCEPTION 'enrolled_course_month_rule_immutable';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER monthly_rule_guard BEFORE UPDATE ON richon.course_month_rules
    FOR EACH ROW EXECUTE FUNCTION richon.freeze_monthly_course_rule();
REVOKE ALL ON richon.course_month_rules,richon.enrollment_learners,richon.monthly_enrollments,richon.monthly_enrollment_terms FROM PUBLIC;
REVOKE ALL ON FUNCTION richon.validate_monthly_term(),richon.freeze_monthly_course_rule() FROM PUBLIC;
