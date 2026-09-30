-- Explicit owner migration only. No long-lived provider token or authorization code is stored.
-- Provider profile values are temporary signup hints and expire with oauth_signups.
ALTER TABLE richon.oauth_signups
  ADD COLUMN provider_name varchar(80),
  ADD COLUMN provider_phone varchar(16),
  ADD COLUMN provider_email varchar(254),
  ADD CONSTRAINT oauth_signups_provider_name_check
    CHECK (provider_name IS NULL OR length(btrim(provider_name)) > 0),
  ADD CONSTRAINT oauth_signups_provider_phone_check
    CHECK (provider_phone IS NULL OR provider_phone ~ '^(01[016789][0-9]{7,8}|\+[1-9][0-9]{7,14})$'),
  ADD CONSTRAINT oauth_signups_provider_email_check
    CHECK (provider_email IS NULL OR provider_email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$');
