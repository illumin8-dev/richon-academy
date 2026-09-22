-- Preparation only. Apply explicitly after review; never on app startup.
-- No existing order/customer row is changed, claimed or linked.
CREATE TABLE richon.members (
    member_id uuid PRIMARY KEY,
    display_name varchar(80) NOT NULL CHECK (length(btrim(display_name)) > 0),
    role varchar(16) NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
    status varchar(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    auth_version bigint NOT NULL DEFAULT 1 CHECK (auth_version > 0),
    terms_version varchar(64) NOT NULL CHECK (length(terms_version) > 0),
    privacy_version varchar(64) NOT NULL CHECK (length(privacy_version) > 0),
    consented_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE richon.auth_identities (
    provider varchar(16) NOT NULL CHECK (provider IN ('kakao', 'naver')),
    app_id varchar(200) NOT NULL CHECK (length(btrim(app_id)) > 0),
    subject varchar(255) NOT NULL CHECK (length(btrim(subject)) > 0),
    member_id uuid NOT NULL REFERENCES richon.members(member_id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider, app_id, subject),
    UNIQUE (member_id, provider, app_id)
);
CREATE TABLE richon.member_sessions (
    token_hash char(64) PRIMARY KEY CHECK (token_hash ~ '^[a-f0-9]{64}$'),
    member_id uuid NOT NULL REFERENCES richon.members(member_id),
    auth_version bigint NOT NULL CHECK (auth_version > 0),
    role_at_issue varchar(16) NOT NULL CHECK (role_at_issue IN ('member', 'admin')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    idle_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at),
    CHECK (idle_expires_at <= expires_at)
);
CREATE INDEX member_sessions_member_idx ON richon.member_sessions(member_id);
CREATE INDEX member_sessions_expiry_idx ON richon.member_sessions(expires_at);
REVOKE ALL ON richon.members, richon.auth_identities, richon.member_sessions FROM PUBLIC;
