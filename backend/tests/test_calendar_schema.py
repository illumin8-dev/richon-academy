"""Central calendar schema contracts; synthetic/static only."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/'migrations'/'018_calendar_events.sql').read_text()

def test_calendar_event_types_and_public_flag_are_explicit():
    assert 'CREATE TABLE richon.calendar_events' in SQL
    for value in ('BRIEFING','STUDY_ALL','SPECIAL','FIELD_TRIP','OTHER'):
        assert value in SQL
    assert 'is_public boolean NOT NULL DEFAULT TRUE' in SQL
    assert 'cancelled_at timestamptz' in SQL
    assert 'version bigint NOT NULL DEFAULT 1' in SQL

def test_calendar_event_time_range_and_public_index():
    assert 'ends_at IS NULL OR ends_at > starts_at' in SQL
    assert 'calendar_events_public_start_idx' in SQL
    assert 'WHERE is_public AND cancelled_at IS NULL' in SQL

def test_migration_does_not_seed_or_delete_customer_data():
    upper=SQL.upper()
    assert 'INSERT INTO' not in upper and 'DELETE FROM' not in upper and 'TRUNCATE' not in upper
    assert 'DROP TABLE' not in upper
