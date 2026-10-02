-- Owner-only legacy roster import ledger. Never exposed to portal runtime.
-- Preserves workbook source rows without creating OAuth members or fabricating identities.

CREATE TABLE richon.legacy_roster_imports (
    batch_id uuid PRIMARY KEY,
    source_name varchar(200) NOT NULL CHECK (length(btrim(source_name)) > 0),
    source_sha256 char(64) NOT NULL UNIQUE CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
    row_count integer NOT NULL CHECK (row_count > 0),
    correction_summary jsonb NOT NULL DEFAULT '[]'::jsonb,
    imported_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE richon.legacy_roster_rows (
    legacy_row_id uuid PRIMARY KEY,
    batch_id uuid NOT NULL REFERENCES richon.legacy_roster_imports(batch_id) ON DELETE RESTRICT,
    learner_id uuid NOT NULL REFERENCES richon.enrollment_learners(learner_id) ON DELETE RESTRICT,
    source_sheet varchar(80) NOT NULL CHECK (length(btrim(source_sheet)) > 0),
    source_row integer NOT NULL CHECK (source_row > 0),
    course_label varchar(100) NOT NULL CHECK (length(btrim(course_label)) > 0),
    purchase_months integer CHECK (purchase_months BETWEEN 1 AND 36),
    amount_krw integer CHECK (amount_krw IS NULL OR amount_krw >= 0),
    payer_name varchar(80),
    email_snapshot varchar(254),
    contact_snapshot varchar(64),
    nickname_snapshot varchar(80),
    joined_on date CHECK (joined_on IS NULL OR isfinite(joined_on)),
    ended_on date CHECK (ended_on IS NULL OR isfinite(ended_on)),
    receipt_issued boolean,
    raw_record jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(batch_id, source_sheet, source_row),
    CHECK (ended_on IS NULL OR joined_on IS NULL OR ended_on >= joined_on)
);

CREATE INDEX legacy_roster_rows_learner_idx
    ON richon.legacy_roster_rows(learner_id, joined_on, ended_on);
CREATE INDEX legacy_roster_rows_course_idx
    ON richon.legacy_roster_rows(course_label, joined_on, ended_on);

REVOKE ALL ON richon.legacy_roster_imports, richon.legacy_roster_rows FROM PUBLIC;
