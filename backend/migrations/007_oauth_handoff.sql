-- Apply explicitly. No provider keys, raw social tokens, or fake users are stored.
CREATE TABLE richon.oauth_attempts (
 state_hash char(64) PRIMARY KEY CHECK(state_hash ~ '^[a-f0-9]{64}$'),
 browser_hash char(64) NOT NULL CHECK(browser_hash ~ '^[a-f0-9]{64}$'),
 provider varchar(8) NOT NULL CHECK(provider IN ('kakao','naver')),
 app_id varchar(200) NOT NULL,
 return_to varchar(64) NOT NULL CHECK(return_to IN ('/portal/mypage','/portal/admin','/portal/enrollments','/portal/manual')),
 expires_at timestamptz NOT NULL,
 consumed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX oauth_attempt_expiry_idx ON richon.oauth_attempts(expires_at);
CREATE TABLE richon.oauth_signups (
 ticket_hash char(64) PRIMARY KEY CHECK(ticket_hash ~ '^[a-f0-9]{64}$'),
 browser_hash char(64) NOT NULL CHECK(browser_hash ~ '^[a-f0-9]{64}$'),
 provider varchar(8) NOT NULL CHECK(provider IN ('kakao','naver')),
 app_id varchar(200) NOT NULL,
 subject varchar(255) NOT NULL,
 display_name varchar(80) NOT NULL,
 return_to varchar(64) NOT NULL CHECK(return_to IN ('/portal/mypage','/portal/admin','/portal/enrollments','/portal/manual')),
 terms_version varchar(64) NOT NULL,
 privacy_version varchar(64) NOT NULL,
 expires_at timestamptz NOT NULL
);
CREATE INDEX oauth_signup_expiry_idx ON richon.oauth_signups(expires_at);
REVOKE ALL ON richon.oauth_attempts,richon.oauth_signups FROM PUBLIC;
