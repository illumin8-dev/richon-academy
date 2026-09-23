"""Synthetic Secret IAM readback regression; no cloud or production database."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from test_login_release_owner import p, policy, setup_run


@pytest.mark.parametrize('version', [None, 0, 1, 3])
def test_default_policy_metadata_is_not_a_permission_change(version):
    before = {'etag': 'old'}
    if version is not None:
        before['version'] = version
    expected = p.with_grant(before)
    actual = {**deepcopy(expected), 'version': 1, 'etag': 'new'}
    assert p.secret_policy_key(actual) == p.secret_policy_key(expected)
    assert before.get('bindings') is None


def test_first_grant_from_empty_policy_accepts_api_version_one(monkeypatch):
    p.reset_report()
    before = {'etag': 'empty'}
    actual = {**p.with_grant(before), 'etag': 'changed', 'version': 1}
    # The previous helper rejected this otherwise-correct response.
    assert p.c.policy_key(actual) != p.c.policy_key(p.with_grant(before))
    monkeypatch.setattr(p, 'secret_policy', Mock(side_effect=[before, actual]))
    write = Mock(); monkeypatch.setattr(p.c, 'gc', write)
    assert p.ensure_grant(p.NAVER[0], before) is True
    write.assert_called_once()


@pytest.mark.parametrize('version', [-1, 2, 4, '1', True])
def test_unknown_policy_versions_remain_rejected(version):
    with pytest.raises(p.c.Stop, match='invalid_secret_policy_version'):
        p.secret_policy_key({'version': version})


def test_conditions_audit_config_and_unknown_fields_are_not_discarded():
    before = policy()
    before['bindings'][0]['condition'] = {'expression': 'false', 'title': 'restricted'}
    before['auditConfigs'] = [{'service': 'allServices', 'auditLogConfigs': [{'logType': 'DATA_READ'}]}]
    original = deepcopy(before)
    desired = p.with_grant(before)
    assert p.secret_policy_key(desired)['version'] == 3
    assert before == original
    for field in ('condition', 'members'):
        changed = deepcopy(desired)
        if field == 'condition':
            changed['bindings'][0][field]['expression'] = 'true'
        else:
            changed['bindings'][0][field].append('user:other@example.invalid')
        assert p.secret_policy_key(changed) != p.secret_policy_key(desired)
    changed = deepcopy(desired); changed['auditConfigs'] = []
    assert p.secret_policy_key(changed) != p.secret_policy_key(desired)
    changed = {**deepcopy(desired), 'unknown': 'not-ignored'}
    assert p.secret_policy_key(changed) != p.secret_policy_key(desired)
    before['version'] = 1
    with pytest.raises(p.c.Stop, match='incomplete_secret_policy_conditions'):
        p.secret_policy_key(before)
    with pytest.raises(p.c.Stop, match='incomplete_secret_policy_conditions'):
        p.secret_policy_key({'bindings': [{'role': p.GRANT + '_withcond_opaque', 'members': []}]})


def test_stale_readback_retries_only_reads(monkeypatch):
    p.reset_report(); before = {'etag': 'old'}
    actual = {**p.with_grant(before), 'version': 1}
    read = Mock(side_effect=[before, before, actual])
    write = Mock(); sleep = Mock()
    monkeypatch.setattr(p, 'secret_policy', read)
    monkeypatch.setattr(p.c, 'gc', write)
    monkeypatch.setattr(p.time, 'sleep', sleep)
    assert p.ensure_grant(p.NAVER[0], before)
    write.assert_called_once(); sleep.assert_called_once_with(1)
    assert 'grant_readback' not in p.REPORT


def test_pending_readback_is_bounded_and_write_not_repeated(monkeypatch):
    p.reset_report(); before = {}
    monkeypatch.setattr(p, 'secret_policy', Mock(return_value=before))
    write = Mock(); sleep = Mock()
    monkeypatch.setattr(p.c, 'gc', write)
    monkeypatch.setattr(p.time, 'sleep', sleep)
    with pytest.raises(p.c.Stop, match='secret_grant_readback_pending'):
        p.ensure_grant(p.NAVER[0], before)
    write.assert_called_once(); assert sleep.call_count == 4
    assert p.REPORT['grant_readback']['old_policy_still_visible'] is True
    assert p.REPORT['naver_runtime_grants'][-1]['status'] == 'write_acknowledged'


def test_unrelated_policy_change_stops_instead_of_retrying(monkeypatch):
    p.reset_report(); before = {}
    changed = p.with_grant(before)
    changed['bindings'][0]['members'].append('user:unexpected@example.invalid')
    monkeypatch.setattr(p, 'secret_policy', Mock(side_effect=[before, changed]))
    write = Mock(); sleep = Mock()
    monkeypatch.setattr(p.c, 'gc', write)
    monkeypatch.setattr(p.time, 'sleep', sleep)
    with pytest.raises(p.c.Stop, match='secret_grant_unexpected_policy'):
        p.ensure_grant(p.NAVER[0], before)
    sleep.assert_not_called(); write.assert_called_once()
    assert 'unexpected@example.invalid' not in str(p.REPORT)


def test_resume_validates_existing_db_without_calling_migration(setup_run, monkeypatch, capsys):
    schema, restricted, migrate, grant = setup_run
    schema.return_value = True
    monkeypatch.setattr('builtins.input', lambda _: 'PREPARE LOGIN')
    assert p.run(apply=True, resume_grants=True) == 0
    migrate.assert_not_called(); assert grant.call_count == 2
    assert schema.call_args_list[0].kwargs == {'require_current': True}
    assert restricted.call_count >= 1
    assert p.REPORT['database_008'] == 'verified_existing'
    assert p.REPORT['server_deployed'] is False
    out = capsys.readouterr().out
    assert 'LOGIN PREREQUISITES READY' in out
    assert 'postgresql://' not in out and 'test-only' not in out


def test_resume_missing_008_stops_before_prompt_or_grants(setup_run, monkeypatch):
    ask = Mock(); monkeypatch.setattr('builtins.input', ask)
    with pytest.raises(p.c.Stop, match='resume_requires_verified_008'):
        p.run(apply=True, resume_grants=True)
    _, _, migrate, grant = setup_run
    ask.assert_not_called(); migrate.assert_not_called(); grant.assert_not_called()


def test_resume_without_apply_is_read_only(setup_run, monkeypatch):
    schema, _, migrate, grant = setup_run; schema.return_value = True
    ask = Mock(); monkeypatch.setattr('builtins.input', ask)
    assert p.run(resume_grants=True) == 0
    ask.assert_not_called(); migrate.assert_not_called(); grant.assert_not_called()


def test_gcloud_requests_pin_richon_project_despite_other_default(monkeypatch):
    monkeypatch.setenv('CLOUDSDK_CORE_PROJECT', 'unrelated-default-project')
    command = Mock(return_value='{"bindings": []}')
    monkeypatch.setattr(p.c, 'command', command)
    p.c.gc('secrets', 'get-iam-policy', p.NAVER[0])
    args = command.call_args.args[0]
    assert '--project=richon-academy' in args
    assert 'unrelated-default-project' not in ' '.join(args)
