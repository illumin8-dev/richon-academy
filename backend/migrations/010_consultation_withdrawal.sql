-- Explicit owner migration only. No runtime DDL or grants; no row deletion.
-- Existing rows get NULL, not a fabricated withdrawal or a changed consent.
ALTER TABLE richon.member_profiles
 ADD COLUMN consultation_withdrawn_at timestamptz,
 ADD CONSTRAINT member_profiles_consultation_withdrawn_check
 CHECK (consultation_withdrawn_at IS NULL OR NOT consultation_consent);
