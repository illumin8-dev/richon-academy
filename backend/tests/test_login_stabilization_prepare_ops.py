"""Safety contract for the owner-run DB012/login stabilization helper."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/'ops/prepare_login_stabilization.py'
spec=importlib.util.spec_from_file_location('prepare_login_stabilization',PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_fixed_scope_and_confirmation():
    assert module.MINIMUM_SOURCE=='36611384f597e47bcda7718209c43d3b411e5984'
    assert module.CONFIRM=='APPLY_DB012'
    source=PATH.read_text()
    assert 'DB012' in source
    assert 'provider_name,provider_phone,provider_email' in source
    assert 'REVOKE UPDATE (name)' in source
    assert 'NO_DEPLOY=YES' in source


def test_helper_does_not_deploy_or_call_providers():
    source=PATH.read_text()
    for forbidden in ('run","deploy','update-traffic','kauth.kakao.com','nid.naver.com/oauth',
                      'kapi.kakao.com','openapi.naver.com'):
        assert forbidden not in source
    assert 'CLOUD_RUN_OR_WORKER_CHANGED=NO' in source


def test_diagnose_branch_precedes_confirmation_and_apply():
    source=PATH.read_text()
    diagnose=source.index('if args.diagnose:')
    confirm=source.index("if input('Type '+CONFIRM+' to continue:")
    apply_call=source.index('changed=apply(owner_url,runtime_url)')
    assert diagnose < confirm < apply_call
    section=source[diagnose:confirm]
    assert 'apply(owner_url,runtime_url)' not in section
    assert 'GRANT INSERT' not in section
    assert 'REVOKE UPDATE' not in section


def test_runtime_contract_removes_member_name_update():
    import portal_readiness as ready
    assert 'name' not in ready.ACCOUNT_UPDATE['member_profiles']
    for field in ('provider_name','provider_phone','provider_email'):
        assert field in ready.INSERT['oauth_signups']
