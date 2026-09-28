-- Explicit owner migration only. Provider demographics remain temporary signup hints.
-- They are persisted to member_profiles only when the user separately opts in to consultation information.
ALTER TABLE richon.oauth_signups
  ADD COLUMN provider_age_range varchar(8),
  ADD COLUMN provider_gender varchar(8),
  ADD CONSTRAINT oauth_signups_provider_age_range_check
    CHECK (provider_age_range IS NULL OR provider_age_range IN
      ('14-19','20-29','30-39','40-49','50-59','60-69','70+')),
  ADD CONSTRAINT oauth_signups_provider_gender_check
    CHECK (provider_gender IS NULL OR provider_gender IN ('female','male'));

GRANT INSERT (provider_age_range, provider_gender)
  ON richon.oauth_signups TO richon_portal_login;
