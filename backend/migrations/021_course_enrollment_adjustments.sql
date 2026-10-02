-- Canonical enrollment adjustment ledger for pause/resume, extension and refunds.
-- Existing enrollments remain the current-state record; every operational change is snapshotted here.
CREATE TABLE richon.course_enrollment_adjustments (
    adjustment_id uuid PRIMARY KEY,
    enrollment_id uuid NOT NULL REFERENCES richon.course_enrollments(enrollment_id) ON DELETE RESTRICT,
    actor_id uuid NOT NULL REFERENCES richon.members(member_id) ON DELETE RESTRICT,
    request_id uuid NOT NULL,
    kind varchar(12) NOT NULL CHECK (kind IN ('SUSPEND','RESUME','EXTEND','REFUND')),
    effective_on date NOT NULL CHECK (isfinite(effective_on)),
    status_before varchar(12) NOT NULL CHECK (status_before IN ('SCHEDULED','ACTIVE','COMPLETED','CANCELLED','SUSPENDED')),
    status_after varchar(12) NOT NULL CHECK (status_after IN ('SCHEDULED','ACTIVE','COMPLETED','CANCELLED','SUSPENDED')),
    access_start_before date NOT NULL CHECK (isfinite(access_start_before)),
    access_end_before date NOT NULL CHECK (isfinite(access_end_before) AND access_end_before >= access_start_before),
    access_start_after date NOT NULL CHECK (isfinite(access_start_after)),
    access_end_after date NOT NULL CHECK (isfinite(access_end_after) AND access_end_after >= access_start_after),
    extension_kind varchar(8) CHECK (extension_kind IN ('FREE','PAID')),
    refund_kind varchar(8) CHECK (refund_kind IN ('FULL','PARTIAL')),
    refund_amount_krw integer CHECK (refund_amount_krw IS NULL OR refund_amount_krw >= 0),
    refund_reference varchar(200),
    note varchar(500) NOT NULL CHECK (length(btrim(note)) > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(actor_id,request_id),
    CHECK (access_start_after = access_start_before),
    CHECK ((kind='REFUND') = (refund_kind IS NOT NULL)),
    CHECK (kind='REFUND' OR (refund_amount_krw IS NULL AND refund_reference IS NULL)),
    CHECK (extension_kind IS NULL OR kind IN ('RESUME','EXTEND')),
    CHECK (kind<>'EXTEND' OR access_end_after > access_end_before),
    CHECK (kind<>'SUSPEND' OR (
        status_after='SUSPENDED' AND access_end_after=access_end_before AND
        extension_kind IS NULL AND refund_kind IS NULL
    )),
    CHECK (kind<>'RESUME' OR status_before='SUSPENDED'),
    CHECK (kind<>'REFUND' OR refund_kind<>'FULL' OR status_after='CANCELLED'),
    CHECK (kind<>'REFUND' OR refund_kind<>'PARTIAL' OR access_end_after < access_end_before)
);
CREATE INDEX course_enrollment_adjustments_enrollment_idx
    ON richon.course_enrollment_adjustments(enrollment_id,created_at,adjustment_id);
REVOKE ALL ON richon.course_enrollment_adjustments FROM PUBLIC;
