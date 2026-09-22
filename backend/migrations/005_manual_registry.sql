-- Explicit migration only; never seeded with real identities or run at startup.
CREATE TABLE richon.manual_learners (
 learner_id uuid PRIMARY KEY REFERENCES richon.enrollment_learners(learner_id),
 original_joined_on date,
 version bigint NOT NULL DEFAULT 1 CHECK(version > 0),
 created_by uuid NOT NULL REFERENCES richon.members(member_id),
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE richon.manual_enrollments (
 enrollment_id uuid PRIMARY KEY REFERENCES richon.monthly_enrollments(enrollment_id),
 version bigint NOT NULL DEFAULT 1 CHECK(version > 0),
 archived_at timestamptz,
 created_by uuid NOT NULL REFERENCES richon.members(member_id),
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE richon.manual_terms (
 term_id uuid PRIMARY KEY REFERENCES richon.monthly_enrollment_terms(term_id),
 created_by uuid NOT NULL REFERENCES richon.members(member_id)
);
CREATE TABLE richon.manual_audit (
 event_id uuid PRIMARY KEY,
 actor_id uuid NOT NULL REFERENCES richon.members(member_id),
 request_id uuid,
 fingerprint char(64),
 operation varchar(32) NOT NULL,
 entity_id varchar(64) NOT NULL,
 reason varchar(200) NOT NULL,
 result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(actor_id, request_id),
 CHECK ((request_id IS NULL AND fingerprint IS NULL) OR
        (request_id IS NOT NULL AND fingerprint ~ '^[a-f0-9]{64}$'))
);
CREATE INDEX manual_audit_entity_idx ON richon.manual_audit(entity_id,created_at);
REVOKE ALL ON richon.manual_learners,richon.manual_enrollments,richon.manual_terms,richon.manual_audit FROM PUBLIC;
-- Existing monthly-term immutability and order consistency guards stay intact.
