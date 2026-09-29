"""Course entitlement schema extension contract; no database access."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/'migrations'/'016_course_entitlements.sql').read_text()
MIGRATE=(ROOT/'course_entitlement_migrate.py').read_text()

def test_extension_preserves_legacy_and_payment_independence():
    upper=SQL.upper()
    assert 'DROP TABLE' not in upper and 'DELETE FROM' not in upper and 'TRUNCATE' not in upper
    assert 'ALTER TABLE richon.course_enrollments' in SQL
    assert 'payment_state' not in SQL

def test_learning_resources_are_optional_https_fields():
    assert 'video_url varchar(2048)' in SQL
    assert 'material_url varchar(2048)' in SQL
    assert "video_url IS NULL OR video_url ~ '^https://'" in SQL
    assert "material_url IS NULL OR material_url ~ '^https://'" in SQL

def test_admin_writes_are_audited_and_idempotent():
    assert 'CREATE TABLE richon.course_domain_audit' in SQL
    assert 'UNIQUE(actor_id,request_id)' in SQL
    assert "fingerprint ~ '^[a-f0-9]{64}$'" in SQL

def test_run_access_is_frozen_only_after_enrollment():
    assert 'enrolled_course_run_access_immutable' in SQL
    assert 'EXISTS(SELECT 1 FROM richon.course_enrollments' in SQL

def test_migration_is_explicit_and_depends_on_015():
    assert "VERSION='016_course_entitlements'" in MIGRATE
    assert "DEPENDENCIES=('015_course_run_foundation',)" in MIGRATE
    assert "if __name__=='__main__':" in MIGRATE
