-- Explicit, additive migration. No customer row, price, or duration is rewritten.
ALTER TABLE richon.monthly_enrollment_terms DROP CONSTRAINT monthly_enrollment_terms_months_check;
ALTER TABLE richon.monthly_enrollment_terms ADD CONSTRAINT monthly_enrollment_terms_months_check CHECK(months IN (1,2,3,6,12));
ALTER TABLE richon.monthly_enrollment_terms ADD COLUMN price_version varchar(64);
CREATE TABLE richon.learner_notes (
 note_id uuid PRIMARY KEY,
 learner_id uuid NOT NULL REFERENCES richon.enrollment_learners(learner_id),
 author_id uuid NOT NULL REFERENCES richon.members(member_id),
 body varchar(2000) NOT NULL CHECK(length(btrim(body))>0),
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX learner_notes_learner_created_idx ON richon.learner_notes(learner_id,created_at,note_id);
REVOKE ALL ON richon.learner_notes FROM PUBLIC;
CREATE OR REPLACE FUNCTION richon.validate_monthly_term() RETURNS trigger LANGUAGE plpgsql AS $$
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
    IF rule_kind IS NULL OR (rule_kind='monthly' AND NEW.months NOT IN (1,2,6)
        AND (TG_OP='INSERT' OR NEW.months IS DISTINCT FROM OLD.months)) OR (rule_kind='fixed' AND NEW.months<>fixed) THEN
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
