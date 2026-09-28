-- Explicit owner migration only. Never invoked by app startup or auto-deploy.
-- CI obtained from the service's own identity-verification flow becomes the
-- canonical duplicate-membership claim. Existing Kakao-origin claims remain valid.
ALTER TABLE richon.member_ci_claims
  DROP CONSTRAINT member_ci_claims_provider_check;

ALTER TABLE richon.member_ci_claims
  ADD CONSTRAINT member_ci_claims_provider_check
    CHECK (provider IN ('kakao','verified'));

COMMENT ON COLUMN richon.member_ci_claims.provider IS
  'kakao=legacy/provider reference, verified=service identity-verification result';
