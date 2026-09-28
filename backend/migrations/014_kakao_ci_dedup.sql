-- Explicit owner migration only. Never invoked by app startup or auto-deploy.
-- Kakao CI is converted to a one-way SHA-256 digest in the provider adapter.
-- The raw CI is never written to PostgreSQL.
ALTER TABLE richon.oauth_signups
  ADD COLUMN provider_ci_digest char(64),
  ADD CONSTRAINT oauth_signups_provider_ci_digest_check
    CHECK (provider_ci_digest IS NULL OR provider_ci_digest ~ '^[a-f0-9]{64}$');

CREATE TABLE richon.member_ci_claims (
  ci_digest char(64) PRIMARY KEY CHECK (ci_digest ~ '^[a-f0-9]{64}$'),
  member_id uuid NOT NULL UNIQUE REFERENCES richon.members(member_id),
  provider varchar(8) NOT NULL CHECK (provider='kakao'),
  created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

REVOKE ALL ON richon.member_ci_claims FROM PUBLIC;
