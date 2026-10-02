"""Enrollment adjustment schema contract; no production database access."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/'migrations'/'021_course_enrollment_adjustments.sql').read_text()
MIGRATE=(ROOT/'course_adjustment_migrate.py').read_text()
PREP=(ROOT.parent/'ops'/'prepare_course_adjustments.py').read_text()


def test_adjustment_ledger_preserves_before_after_snapshots():
    for column in (
        'status_before','status_after','access_start_before','access_end_before',
        'access_start_after','access_end_after','effective_on','note',
    ):
        assert column in SQL
    assert "kind IN ('SUSPEND','RESUME','EXTEND','REFUND')" in SQL


def test_refund_and_extension_metadata_are_explicit():
    assert "extension_kind varchar(8)" in SQL
    assert "refund_kind varchar(8)" in SQL
    assert 'refund_amount_krw integer' in SQL
    assert 'refund_reference varchar(200)' in SQL
    assert "refund_kind IN ('FULL','PARTIAL')" in SQL
    assert "extension_kind IN ('FREE','PAID')" in SQL


def test_adjustments_never_delete_enrollment_history():
    upper=SQL.upper()
    assert 'ON DELETE CASCADE' not in upper
    assert 'DELETE FROM' not in upper
    assert 'TRUNCATE' not in upper


def test_adjustment_migration_is_explicit_and_course_scoped():
    assert "VERSION='021_course_enrollment_adjustments'" in MIGRATE
    assert "DEPENDENCIES=('016_course_entitlements',)" in MIGRATE
    assert 'advisory_slot=7' in MIGRATE
    assert "if __name__=='__main__':" in MIGRATE


def test_db021_prepare_changes_only_incremental_course_grants():
    assert 'grant_adjustment_delta' in PREP
    assert 'course.grant_course' not in PREP
    assert "'course_enrollment_adjustments'" in PREP
    assert "'access_end'" in PREP
    assert 'REVOKE ALL ON {} FROM {}' in PREP
    assert 'richon.course_enrollments' in PREP
