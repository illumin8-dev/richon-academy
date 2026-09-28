-- New canonical learning domain. Legacy monthly/manual tables remain intact.
-- No production courses, members, learners or enrollments are seeded here.

CREATE TABLE richon.course_programs (
    program_id varchar(64) PRIMARY KEY CHECK (program_id ~ '^[a-z0-9][a-z0-9_-]*$'),
    title varchar(200) NOT NULL CHECK (length(btrim(title)) > 0),
    access_mode varchar(16) NOT NULL CHECK (access_mode IN ('fixed_months','date_range')),
    fixed_months integer,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((access_mode='fixed_months' AND fixed_months BETWEEN 1 AND 36)
        OR (access_mode='date_range' AND fixed_months IS NULL))
);

CREATE TABLE richon.course_runs (
    run_id uuid PRIMARY KEY,
    program_id varchar(64) NOT NULL REFERENCES richon.course_programs(program_id),
    cohort_label varchar(100),
    starts_on date NOT NULL CHECK (isfinite(starts_on)),
    ends_on date NOT NULL CHECK (isfinite(ends_on) AND ends_on >= starts_on),
    default_access_start date NOT NULL CHECK (isfinite(default_access_start)),
    default_access_end date NOT NULL CHECK (isfinite(default_access_end) AND default_access_end >= default_access_start),
    recruit_opens_at timestamptz,
    recruit_closes_at timestamptz,
    capacity integer CHECK (capacity IS NULL OR capacity BETWEEN 1 AND 100000),
    status varchar(12) NOT NULL CHECK (status IN ('OPEN','WAITLIST','UPCOMING','CLOSED')),
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (recruit_closes_at IS NULL OR recruit_opens_at IS NULL OR recruit_closes_at >= recruit_opens_at)
);
CREATE INDEX course_runs_program_status_idx ON richon.course_runs(program_id,status,starts_on);

CREATE TABLE richon.course_sessions (
    session_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES richon.course_runs(run_id) ON DELETE RESTRICT,
    sequence_no integer NOT NULL CHECK (sequence_no BETWEEN 1 AND 1000),
    title varchar(200) NOT NULL CHECK (length(btrim(title)) > 0),
    mentor_name varchar(80),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz,
    content_url varchar(2048),
    cancelled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id,sequence_no),
    CHECK (ends_at IS NULL OR ends_at > starts_at),
    CHECK (content_url IS NULL OR content_url ~ '^https://')
);
CREATE INDEX course_sessions_run_start_idx ON richon.course_sessions(run_id,starts_at);

CREATE TABLE richon.course_enrollments (
    enrollment_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES richon.course_runs(run_id),
    learner_id uuid NOT NULL REFERENCES richon.enrollment_learners(learner_id),
    status varchar(12) NOT NULL CHECK (status IN ('SCHEDULED','ACTIVE','COMPLETED','CANCELLED','SUSPENDED')),
    access_start date NOT NULL CHECK (isfinite(access_start)),
    access_end date NOT NULL CHECK (isfinite(access_end) AND access_end >= access_start),
    source varchar(16) NOT NULL CHECK (source IN ('ADMIN','LEGACY','INVITE','PAYMENT')),
    note varchar(500),
    cancelled_at timestamptz,
    suspended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id,learner_id),
    CHECK ((status='CANCELLED')=(cancelled_at IS NOT NULL)),
    CHECK ((status='SUSPENDED')=(suspended_at IS NOT NULL))
);
CREATE INDEX course_enrollments_learner_idx ON richon.course_enrollments(learner_id,status,access_end);
CREATE INDEX course_enrollments_run_idx ON richon.course_enrollments(run_id,status);

CREATE FUNCTION richon.validate_course_enrollment_access() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE mode text; months integer; run_start date; run_end date;
BEGIN
    SELECT p.access_mode,p.fixed_months,r.default_access_start,r.default_access_end
      INTO mode,months,run_start,run_end
      FROM richon.course_runs r JOIN richon.course_programs p USING(program_id)
     WHERE r.run_id=NEW.run_id
     FOR SHARE OF r,p;
    IF mode IS NULL THEN RAISE EXCEPTION 'course_run_not_found'; END IF;
    IF mode='fixed_months' THEN
        IF NEW.access_start IS DISTINCT FROM run_start
           OR NEW.access_end IS DISTINCT FROM (run_start + make_interval(months=>months) - interval '1 day')::date THEN
            RAISE EXCEPTION 'fixed_access_window_mismatch';
        END IF;
    ELSE
        IF NEW.access_start < run_start OR NEW.access_end > run_end THEN
            RAISE EXCEPTION 'date_range_access_outside_run';
        END IF;
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER course_enrollment_access_guard
BEFORE INSERT OR UPDATE OF run_id,access_start,access_end ON richon.course_enrollments
FOR EACH ROW EXECUTE FUNCTION richon.validate_course_enrollment_access();

REVOKE ALL ON richon.course_programs,richon.course_runs,richon.course_sessions,richon.course_enrollments FROM PUBLIC;
REVOKE ALL ON FUNCTION richon.validate_course_enrollment_access() FROM PUBLIC;
