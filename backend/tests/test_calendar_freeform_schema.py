"""DB019 free-form calendar schema contract; static/synthetic only."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/'migrations'/'019_calendar_freeform.sql').read_text()

def test_freeform_calendar_adds_only_display_fields():
    for value in ('course_label varchar(200)','content_text varchar(500)','color_hex varchar(7)'):
        assert value in SQL
    assert "color_hex ~ '^#[0-9A-Fa-f]{6}$'" in SQL

def test_freeform_migration_does_not_link_course_tables_or_rewrite_rows():
    upper=SQL.upper()
    assert 'COURSE_RUNS' not in upper and 'COURSE_SESSIONS' not in upper
    assert 'UPDATE ' not in upper and 'DELETE FROM' not in upper and 'TRUNCATE' not in upper
    assert 'DROP TABLE' not in upper and 'DROP COLUMN' not in upper
