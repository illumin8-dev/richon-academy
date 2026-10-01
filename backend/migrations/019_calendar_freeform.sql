-- Free-form admin calendar extension.
-- DB018 calendar_events remains the physical table; course/session relations are not added.
ALTER TABLE richon.calendar_events
    ADD COLUMN course_label varchar(200) NOT NULL DEFAULT '일정',
    ADD COLUMN content_text varchar(500) NOT NULL DEFAULT '',
    ADD COLUMN color_hex varchar(7) NOT NULL DEFAULT '#777777';

ALTER TABLE richon.calendar_events
    ALTER COLUMN course_label DROP DEFAULT,
    ALTER COLUMN content_text DROP DEFAULT,
    ALTER COLUMN color_hex DROP DEFAULT;

ALTER TABLE richon.calendar_events
    ADD CONSTRAINT calendar_events_color_hex
    CHECK (color_hex ~ '^#[0-9A-Fa-f]{6}$');
