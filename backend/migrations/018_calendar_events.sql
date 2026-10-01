-- Central calendar events that are not tied to a course run/session.
-- Course sessions remain the canonical source for real class meetings.
CREATE TABLE richon.calendar_events (
    event_id uuid PRIMARY KEY,
    event_type varchar(16) NOT NULL CHECK (event_type IN ('BRIEFING','STUDY_ALL','SPECIAL','FIELD_TRIP','OTHER')),
    title varchar(200) NOT NULL CHECK (length(btrim(title)) > 0),
    presenter_name varchar(80),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz,
    is_public boolean NOT NULL DEFAULT TRUE,
    cancelled_at timestamptz,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (ends_at IS NULL OR ends_at > starts_at)
);
CREATE INDEX calendar_events_start_idx ON richon.calendar_events(starts_at,event_id);
CREATE INDEX calendar_events_public_start_idx ON richon.calendar_events(starts_at,event_id)
    WHERE is_public AND cancelled_at IS NULL;

REVOKE ALL ON richon.calendar_events FROM PUBLIC;
