-- Explicit owner-applied forward migration. Do not edit applied migration 007.
-- Only add three exact static-page destinations; no arbitrary URLs or row edits.
ALTER TABLE richon.oauth_attempts
 DROP CONSTRAINT oauth_attempts_return_to_check,
 ADD CONSTRAINT oauth_attempts_return_to_check CHECK(return_to IN (
  '/','/index.html','/apply.html',
  '/portal/mypage','/portal/admin','/portal/enrollments','/portal/manual'));
ALTER TABLE richon.oauth_signups
 DROP CONSTRAINT oauth_signups_return_to_check,
 ADD CONSTRAINT oauth_signups_return_to_check CHECK(return_to IN (
  '/','/index.html','/apply.html',
  '/portal/mypage','/portal/admin','/portal/enrollments','/portal/manual'));
