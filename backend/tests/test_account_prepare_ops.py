"""Safety contract for the owner-run DB010 production preparation helper."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/'ops/prepare_account_lifecycle.py'
spec=importlib.util.spec_from_file_location('prepare_account_lifecycle',PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def dsn(user='neondb_owner',host='ep-gentle-night-b3h5xlji.c-4.ap-southeast-1.aws.neon.tech'):
    return f'postgresql://{user}:synthetic-secret@{host}/neondb?sslmode=require&channel_binding=require'


def test_fixed_targets_and_explicit_confirmation():
    assert module.PROJECT=='richon-academy'
    assert module.PROJECT_NUMBER=='756298505437'
    assert module.REGION=='asia-southeast1'
    assert module.OWNER_SERVICE=='richon-backend-test'
    assert module.PORTAL_SERVICE=='richon-portal'
    assert module.CONFIRM=='APPLY_DB010'
    assert module.MINIMUM_SOURCE=='38013be54f5584a857c7485d709f00baf632b597'


def test_dsn_validation_is_fixed_to_known_neon_database_and_roles():
    assert module.validate_dsn(dsn(),'neondb_owner').path=='/neondb'
    assert module.validate_dsn(dsn('richon_portal_login'),'richon_portal_login').path=='/neondb'
    for value,role in [
        (dsn(host='evil.invalid'),'neondb_owner'),
        (dsn('wrong_role'),'neondb_owner'),
        ('postgresql://neondb_owner:x@ep-gentle-night-b3h5xlji.c-4.ap-southeast-1.aws.neon.tech/other?sslmode=require','neondb_owner'),
        ('postgresql://neondb_owner:x@ep-gentle-night-b3h5xlji.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&x=1','neondb_owner'),
    ]:
        with pytest.raises(module.Stop):
            module.validate_dsn(value,role)


def test_helper_cannot_deploy_or_enable_account_feature():
    source=PATH.read_text()
    assert 'run","deploy' not in source
    assert '--set-env-vars' not in source
    assert 'RICHON_ACCOUNT_ENABLED":"true' not in source
    assert 'account_feature_already_enabled' in source
    assert 'NO_DEPLOY=YES' in source


def test_retained_records_stay_write_only_in_readiness_contract():
    import portal_readiness as ready
    assert ready.ACCOUNT_WRITE_ONLY==('retained_order_records',)
    assert 'retained_order_records' in ready.ACCOUNT_INSERT
    assert 'retained_order_records' not in ready.ACCOUNT_READ


def test_database_failures_are_reported_as_fixed_safe_stage_codes():
    source=PATH.read_text()
    for code in (
        'owner_preflight_connection_failed',
        'runtime_preflight_connection_failed',
        'db010_transaction_failed',
        'runtime_readback_failed',
        'owner_final_readback_failed',
    ):
        assert code in source
    assert 'str(exc)' not in source or 'isinstance(exc,Stop)' in source


class FakeConnectionError(Exception):
    sqlstate=None

@pytest.mark.parametrize("message,expected",[
    ("password authentication failed for user", "owner_authentication_failed"),
    ("certificate verify failed", "owner_tls_verification_failed"),
    ("could not translate host name", "owner_dns_failed"),
    ("connection timed out", "owner_connection_timeout"),
    ("connection refused", "owner_connection_refused"),
    ("channel binding required", "owner_channel_binding_failed"),
    ("compute endpoint unavailable", "owner_neon_endpoint_unavailable"),
    ("something else", "owner_connection_failed_unknown"),
])
def test_connection_failure_code_is_fixed_and_non_secret(message,expected):
    error=FakeConnectionError(message)
    assert module.connection_failure_code("owner",error)==expected
    assert "synthetic-secret" not in module.connection_failure_code("owner",error)

def test_diagnose_mode_is_read_only_by_construction():
    source=PATH.read_text()
    assert '"--diagnose"' in source
    assert 'DIAGNOSE_ONLY=PASS / NO_DATABASE_CHANGES=YES' in source
    diagnose_section=source[source.index('if args.diagnose:'):source.index('if input("Type "+CONFIRM')]
    assert 'apply(' not in diagnose_section
    assert 'GRANT ' not in diagnose_section
    assert 'INSERT INTO' not in diagnose_section
