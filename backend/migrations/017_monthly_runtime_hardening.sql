-- Runtime hardening for DB004 term validation.
-- The portal runtime cannot update monthly enrollment identity/course rules, so
-- validation reads them without row-lock clauses that would require UPDATE ACLs.
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
      WHERE e.enrollment_id=NEW.enrollment_id;
    SELECT duration_kind,fixed_months INTO rule_kind,fixed
      FROM richon.course_month_rules WHERE course_id=course;
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
        IF owner_member IS NOT NULL AND owner_member IS DISTINCT FROM learner_member THEN
            RAISE EXCEPTION 'order_owner_mismatch';
        END IF;
    END IF;
    RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION richon.validate_monthly_term() FROM PUBLIC;
