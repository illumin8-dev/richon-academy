-- Explicit owner migration only. Never invoked by app startup or auto-deploy.
-- Optional advertising-message consent remains feature-gated until this table and
-- exact runtime grants are prepared.
CREATE TABLE richon.member_marketing_consents (
 member_id uuid PRIMARY KEY REFERENCES richon.members(member_id),
 email_enabled boolean NOT NULL,
 sms_enabled boolean NOT NULL,
 consent_version varchar(64) NOT NULL CHECK (consent_version='marketing-v1'),
 last_consented_at timestamptz,
 last_withdrawn_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK (email_enabled = sms_enabled),
 CHECK (NOT email_enabled OR last_consented_at IS NOT NULL)
);
REVOKE ALL ON richon.member_marketing_consents FROM PUBLIC;
