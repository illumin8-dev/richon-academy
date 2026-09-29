-- Canonical course-domain extension. Requires 015 and preserves all legacy tables.
ALTER TABLE richon.course_programs
    ADD COLUMN description varchar(500),
    ADD COLUMN version bigint NOT NULL DEFAULT 1 CHECK(version > 0);

ALTER TABLE richon.course_runs
    ADD COLUMN price_krw integer NOT NULL DEFAULT 0 CHECK(price_krw BETWEEN 0 AND 100000000),
    ADD COLUMN version bigint NOT NULL DEFAULT 1 CHECK(version > 0);

ALTER TABLE richon.course_sessions
    ADD COLUMN video_url varchar(2048),
    ADD COLUMN material_url varchar(2048),
    ADD COLUMN version bigint NOT NULL DEFAULT 1 CHECK(version > 0),
    ADD CHECK (video_url IS NULL OR video_url ~ '^https://'),
    ADD CHECK (material_url IS NULL OR material_url ~ '^https://');

ALTER TABLE richon.course_enrollments
    ADD COLUMN version bigint NOT NULL DEFAULT 1 CHECK(version > 0);

CREATE TABLE richon.course_domain_audit (
    event_id uuid PRIMARY KEY,
    actor_id uuid NOT NULL REFERENCES richon.members(member_id),
    request_id uuid NOT NULL,
    fingerprint char(64) NOT NULL CHECK(fingerprint ~ '^[a-f0-9]{64}$'),
    operation varchar(32) NOT NULL,
    entity_id varchar(64) NOT NULL,
    reason varchar(200) NOT NULL,
    result jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(actor_id,request_id)
);
CREATE INDEX course_domain_audit_entity_idx ON richon.course_domain_audit(entity_id,created_at);

CREATE FUNCTION richon.validate_course_run_defaults() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE mode text; months integer;
BEGIN
    SELECT access_mode,fixed_months INTO mode,months
      FROM richon.course_programs WHERE program_id=NEW.program_id FOR SHARE;
    IF mode IS NULL THEN RAISE EXCEPTION 'course_program_not_found'; END IF;
    IF mode='fixed_months'
       AND NEW.default_access_end IS DISTINCT FROM
           (NEW.default_access_start + make_interval(months=>months) - interval '1 day')::date THEN
        RAISE EXCEPTION 'fixed_run_access_window_mismatch';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER course_run_defaults_guard
BEFORE INSERT OR UPDATE OF program_id,default_access_start,default_access_end ON richon.course_runs
FOR EACH ROW EXECUTE FUNCTION richon.validate_course_run_defaults();

CREATE FUNCTION richon.freeze_course_run_access() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.program_id,NEW.starts_on,NEW.ends_on,NEW.default_access_start,NEW.default_access_end)
       IS DISTINCT FROM
       (OLD.program_id,OLD.starts_on,OLD.ends_on,OLD.default_access_start,OLD.default_access_end)
       AND EXISTS(SELECT 1 FROM richon.course_enrollments WHERE run_id=OLD.run_id) THEN
        RAISE EXCEPTION 'enrolled_course_run_access_immutable';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER course_run_access_freeze
BEFORE UPDATE ON richon.course_runs
FOR EACH ROW EXECUTE FUNCTION richon.freeze_course_run_access();

REVOKE ALL ON richon.course_domain_audit FROM PUBLIC;
REVOKE ALL ON FUNCTION richon.validate_course_run_defaults(),richon.freeze_course_run_access() FROM PUBLIC;
