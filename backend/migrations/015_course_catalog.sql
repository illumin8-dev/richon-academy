-- New course catalog foundation. No legacy rows are migrated or deleted here.
-- Existing richon.courses/monthly_* tables remain the legacy source until an explicit later migration.
CREATE TABLE richon.course_programs (
    program_id uuid PRIMARY KEY,
    title varchar(200) NOT NULL CHECK (length(btrim(title)) > 0),
    description varchar(1200),
    access_kind varchar(20) NOT NULL CHECK (access_kind IN ('fixed_months','date_range')),
    fixed_months integer CHECK (fixed_months BETWEEN 1 AND 24),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((access_kind='fixed_months' AND fixed_months IS NOT NULL)
        OR (access_kind='date_range' AND fixed_months IS NULL))
);

CREATE TABLE richon.course_runs (
    run_id uuid PRIMARY KEY,
    program_id uuid NOT NULL REFERENCES richon.course_programs(program_id),
    cohort varchar(100),
    status varchar(16) NOT NULL CHECK (status IN ('UPCOMING','OPEN','WAITLIST','CLOSED')),
    starts_on date NOT NULL CHECK (isfinite(starts_on)),
    ends_on date NOT NULL CHECK (isfinite(ends_on) AND ends_on >= starts_on),
    default_access_start date CHECK (default_access_start IS NULL OR isfinite(default_access_start)),
    default_access_end date CHECK (default_access_end IS NULL OR isfinite(default_access_end)),
    recruitment_open_at timestamptz,
    recruitment_close_at timestamptz,
    capacity integer CHECK (capacity IS NULL OR capacity BETWEEN 1 AND 100000),
    price_krw integer NOT NULL DEFAULT 0 CHECK (price_krw BETWEEN 0 AND 100000000),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((default_access_start IS NULL) = (default_access_end IS NULL)),
    CHECK (default_access_end IS NULL OR default_access_end >= default_access_start),
    CHECK (recruitment_open_at IS NULL OR recruitment_close_at IS NULL OR recruitment_close_at >= recruitment_open_at)
);
CREATE INDEX course_runs_program_idx ON richon.course_runs(program_id,starts_on DESC);
CREATE INDEX course_runs_status_idx ON richon.course_runs(status,archived_at);

CREATE TABLE richon.course_sessions (
    session_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES richon.course_runs(run_id),
    sequence_no integer NOT NULL CHECK (sequence_no BETWEEN 1 AND 1000),
    title varchar(200) NOT NULL CHECK (length(btrim(title)) > 0),
    mentor_name varchar(80),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz,
    content_url varchar(2048),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id,sequence_no),
    CHECK (ends_at IS NULL OR ends_at > starts_at),
    CHECK (content_url IS NULL OR content_url ~ '^https://')
);
CREATE INDEX course_sessions_run_time_idx ON richon.course_sessions(run_id,starts_at);

CREATE TABLE richon.run_enrollments (
    enrollment_id uuid PRIMARY KEY,
    learner_id uuid NOT NULL REFERENCES richon.enrollment_learners(learner_id),
    run_id uuid NOT NULL REFERENCES richon.course_runs(run_id),
    access_start date NOT NULL CHECK (isfinite(access_start)),
    access_end date NOT NULL CHECK (isfinite(access_end) AND access_end >= access_start),
    status varchar(16) NOT NULL CHECK (status IN ('SCHEDULED','ACTIVE','COMPLETED','CANCELLED','SUSPENDED')),
    source varchar(20) NOT NULL CHECK (source IN ('manual','legacy','complimentary','payment')),
    source_ref varchar(200),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    created_by uuid REFERENCES richon.members(member_id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(learner_id,run_id)
);
CREATE INDEX run_enrollments_run_status_idx ON richon.run_enrollments(run_id,status);
CREATE INDEX run_enrollments_learner_idx ON richon.run_enrollments(learner_id,access_end DESC);

CREATE TABLE richon.course_catalog_audit (
    event_id uuid PRIMARY KEY,
    actor_id uuid NOT NULL REFERENCES richon.members(member_id),
    request_id uuid NOT NULL,
    fingerprint char(64) NOT NULL CHECK (fingerprint ~ '^[a-f0-9]{64}$'),
    operation varchar(32) NOT NULL,
    entity_id varchar(64) NOT NULL,
    reason varchar(200) NOT NULL,
    result jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(actor_id,request_id)
);
CREATE INDEX course_catalog_audit_entity_idx ON richon.course_catalog_audit(entity_id,created_at DESC);

CREATE FUNCTION richon.validate_course_run_access() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind text; months integer; expected date;
BEGIN
    SELECT access_kind,fixed_months INTO kind,months
      FROM richon.course_programs
      WHERE program_id=NEW.program_id AND archived_at IS NULL;
    IF kind IS NULL THEN RAISE EXCEPTION 'program_unavailable'; END IF;
    IF kind='fixed_months' THEN
        IF NEW.default_access_start IS NULL OR NEW.default_access_end IS NULL THEN
            RAISE EXCEPTION 'fixed_access_period_required';
        END IF;
        expected=(NEW.default_access_start + make_interval(months=>months) - interval '1 day')::date;
        IF NEW.default_access_end<>expected THEN RAISE EXCEPTION 'fixed_access_period_mismatch'; END IF;
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER course_run_access_guard BEFORE INSERT OR UPDATE OF program_id,default_access_start,default_access_end
    ON richon.course_runs FOR EACH ROW EXECUTE FUNCTION richon.validate_course_run_access();

CREATE FUNCTION richon.freeze_program_access_policy() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.access_kind,NEW.fixed_months) IS DISTINCT FROM (OLD.access_kind,OLD.fixed_months)
       AND EXISTS(SELECT 1 FROM richon.course_runs WHERE program_id=OLD.program_id) THEN
        RAISE EXCEPTION 'program_access_policy_in_use';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER course_program_policy_guard BEFORE UPDATE OF access_kind,fixed_months
    ON richon.course_programs FOR EACH ROW EXECUTE FUNCTION richon.freeze_program_access_policy();

CREATE FUNCTION richon.validate_run_enrollment_access() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind text; months integer; expected date;
BEGIN
    SELECT p.access_kind,p.fixed_months INTO kind,months
      FROM richon.course_runs r JOIN richon.course_programs p USING(program_id)
      WHERE r.run_id=NEW.run_id AND r.archived_at IS NULL AND p.archived_at IS NULL;
    IF kind IS NULL THEN RAISE EXCEPTION 'run_unavailable'; END IF;
    IF kind='fixed_months' THEN
        expected=(NEW.access_start + make_interval(months=>months) - interval '1 day')::date;
        IF NEW.access_end<>expected THEN RAISE EXCEPTION 'fixed_enrollment_period_mismatch'; END IF;
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER run_enrollment_access_guard BEFORE INSERT OR UPDATE OF run_id,access_start,access_end
    ON richon.run_enrollments FOR EACH ROW EXECUTE FUNCTION richon.validate_run_enrollment_access();

REVOKE ALL ON richon.course_programs,richon.course_runs,richon.course_sessions,
    richon.run_enrollments,richon.course_catalog_audit FROM PUBLIC;
REVOKE ALL ON FUNCTION richon.validate_course_run_access(),richon.freeze_program_access_policy(),
    richon.validate_run_enrollment_access() FROM PUBLIC;
