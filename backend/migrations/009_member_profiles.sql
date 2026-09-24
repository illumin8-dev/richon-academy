-- Explicit owner migration only. Never invoked by app startup or auto-deploy.
-- No existing member, order, identity or session rows are rewritten.
CREATE TABLE richon.member_profiles (
 member_id uuid PRIMARY KEY REFERENCES richon.members(member_id),
 name varchar(80) NOT NULL CHECK (length(btrim(name)) > 0),
 phone varchar(16) NOT NULL CHECK (phone ~ '^(01[016789][0-9]{7,8}|\+[1-9][0-9]{7,14})$'),
 email varchar(254) NOT NULL CHECK (email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
 age_range varchar(8) CHECK (age_range IN ('14-19','20-29','30-39','40-49','50-59','60-69','70+')),
 gender varchar(8) CHECK (gender IN ('female','male')),
 consultation_consent boolean NOT NULL,
 over14_confirmed boolean NOT NULL CHECK (over14_confirmed),
 terms_version varchar(64) NOT NULL CHECK (terms_version='member-info-v1'),
 privacy_version varchar(64) NOT NULL CHECK (privacy_version='member-info-v1'),
 consented_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK (consultation_consent OR (age_range IS NULL AND gender IS NULL))
);
REVOKE ALL ON richon.member_profiles FROM PUBLIC;
-- No unique contact indexes: shared email/telephone does not imply one identity.
