-- Explicit owner migration only. Account actions remain disabled until runtime grants are prepared.
-- Existing operational orders are preserved, but withdrawal moves required transaction PII
-- into a separately permissioned retention table before scrubbing the operational copy.
ALTER TABLE richon.members
    DROP CONSTRAINT members_status_check,
    ADD CONSTRAINT members_status_check CHECK (status IN ('active','disabled','withdrawn')),
    ADD COLUMN withdrawn_at timestamptz,
    ADD CONSTRAINT members_withdrawn_at_check CHECK (
        (status='withdrawn' AND withdrawn_at IS NOT NULL)
        OR (status<>'withdrawn' AND withdrawn_at IS NULL)
    );

CREATE TABLE richon.oauth_account_attempts (
    state_hash char(64) PRIMARY KEY CHECK (state_hash ~ '^[a-f0-9]{64}$'),
    browser_hash char(64) NOT NULL CHECK (browser_hash ~ '^[a-f0-9]{64}$'),
    member_id uuid NOT NULL REFERENCES richon.members(member_id),
    provider varchar(8) NOT NULL CHECK (provider IN ('kakao','naver')),
    app_id varchar(200) NOT NULL CHECK (length(btrim(app_id))>0),
    action varchar(10) NOT NULL CHECK (action IN ('link','reauth','unlink','withdraw')),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX oauth_account_attempt_expiry_idx ON richon.oauth_account_attempts(expires_at);
CREATE INDEX oauth_account_attempt_member_idx ON richon.oauth_account_attempts(member_id,created_at);

CREATE TABLE richon.oauth_link_confirmations (
    ticket_hash char(64) PRIMARY KEY CHECK (ticket_hash ~ '^[a-f0-9]{64}$'),
    browser_hash char(64) NOT NULL CHECK (browser_hash ~ '^[a-f0-9]{64}$'),
    member_id uuid NOT NULL REFERENCES richon.members(member_id),
    provider varchar(8) NOT NULL CHECK (provider IN ('kakao','naver')),
    app_id varchar(200) NOT NULL CHECK (length(btrim(app_id))>0),
    subject varchar(255) NOT NULL CHECK (length(btrim(subject))>0),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(member_id,provider,app_id)
);
CREATE INDEX oauth_link_confirmation_expiry_idx ON richon.oauth_link_confirmations(expires_at);

CREATE TABLE richon.account_withdrawals (
    member_id uuid PRIMARY KEY REFERENCES richon.members(member_id),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Safe-code-only provider unlink failures. Raw provider responses and tokens are never stored.
CREATE TABLE richon.provider_unlink_failures (
    event_id uuid PRIMARY KEY,
    member_id uuid NOT NULL REFERENCES richon.members(member_id),
    provider varchar(8) NOT NULL CHECK (provider IN ('kakao','naver')),
    safe_code varchar(32) NOT NULL CHECK (safe_code IN ('provider_unavailable')),
    expires_at timestamptz NOT NULL DEFAULT (CURRENT_TIMESTAMP + interval '30 days'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX provider_unlink_failures_member_idx ON richon.provider_unlink_failures(member_id,created_at);

-- Legally retained transaction PII is isolated from the normal order read model.
-- The portal runtime receives INSERT only, never SELECT/UPDATE/DELETE, on this table.
CREATE TABLE richon.retained_order_records (
    order_id varchar(36) PRIMARY KEY,
    member_id uuid NOT NULL REFERENCES richon.members(member_id),
    course_id varchar(64) NOT NULL,
    course_title varchar(200) NOT NULL,
    cohort varchar(100),
    amount_krw integer NOT NULL CHECK (amount_krw > 0),
    currency varchar(3) NOT NULL CHECK (currency='KRW'),
    status varchar(32) NOT NULL,
    customer_name varchar(80) NOT NULL,
    customer_phone varchar(11) NOT NULL,
    customer_email varchar(254) NOT NULL,
    order_created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    retained_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at >= order_created_at + interval '5 years')
);
CREATE INDEX retained_order_records_expiry_idx ON richon.retained_order_records(expires_at);

REVOKE ALL ON richon.oauth_account_attempts,richon.oauth_link_confirmations,
    richon.account_withdrawals,richon.provider_unlink_failures,
    richon.retained_order_records FROM PUBLIC;
