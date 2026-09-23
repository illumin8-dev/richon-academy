"""Owner helper with mocked metadata only. Never uses real IAM or credentials."""
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import prepare_login_release as p


def policy():
    return {'version':3,'etag':'opaque','bindings':[{'role':p.GRANT,'members':['serviceAccount:other@example.invalid']} ]}


def test_grant_is_exact_and_does_not_mutate_other_members():
    before=policy(); original=deepcopy(before)
    after=p.with_grant(before)
    assert after['bindings'][0]['members'] == ['serviceAccount:other@example.invalid',p.RUNTIME_MEMBER]
    assert p.has_grant(after)
    assert p.with_grant(after)==after and before==original


def test_conditional_binding_does_not_silently_count_as_unconditional():
    before={'bindings':[{'role':p.GRANT,'members':[p.RUNTIME_MEMBER],'condition':{'expression':'false'}}]}
    assert not p.has_grant(before)
    after=p.with_grant(before)
    assert len(after['bindings'])==2 and after['bindings'][0]==before['bindings'][0]


def test_existing_grant_is_read_only(monkeypatch):
    before=p.with_grant(policy())
    monkeypatch.setattr(p,'secret_policy',lambda _:before)
    call=Mock();monkeypatch.setattr(p.c,'gc',call)
    assert p.ensure_grant(p.NAVER[0],before) is False
    call.assert_not_called()


def test_changed_policy_stops_before_grant(monkeypatch):
    monkeypatch.setattr(p,'secret_policy',lambda _:{'bindings':[]})
    call=Mock();monkeypatch.setattr(p.c,'gc',call)
    with pytest.raises(p.c.Stop,match='secret_policy_changed'):p.ensure_grant(p.NAVER[0],policy())
    call.assert_not_called()


def test_new_grant_has_only_runtime_member_and_secret_scope(monkeypatch):
    before=policy(); after=p.with_grant(before)
    read=Mock(side_effect=[before,after]);monkeypatch.setattr(p,'secret_policy',read)
    call=Mock();monkeypatch.setattr(p.c,'gc',call)
    assert p.ensure_grant(p.NAVER[0],before)
    assert call.call_args.args == ('secrets','add-iam-policy-binding',p.NAVER[0],
                                   '--member='+p.RUNTIME_MEMBER,'--role='+p.GRANT,'--condition=None')


def test_naver_secret_payload_requests_always_refused(monkeypatch):
    call=Mock();monkeypatch.setattr(p.c,'command',call)
    for name in p.NAVER:
        with pytest.raises(p.c.Stop):p.secret_text(name,'1')
    call.assert_not_called()


def test_versions_need_enabled_numeric_metadata(monkeypatch):
    monkeypatch.setattr(p.c,'gc',lambda *a:[{'name':f'projects/{p.c.NUMBER}/secrets/{p.NAVER[0]}/versions/2','state':'ENABLED'},
                                         {'name':f'projects/{p.c.NUMBER}/secrets/{p.NAVER[0]}/versions/11','state':'ENABLED'}])
    assert p.secret_version(p.NAVER[0])=='11'
    monkeypatch.setattr(p.c,'gc',lambda *a:[])
    with pytest.raises(p.c.Stop):p.secret_version(p.NAVER[0])
    with pytest.raises(p.c.Stop):p.secret_version('unrelated')


def test_actions_cannot_run_owner_setup(monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    call=Mock();monkeypatch.setattr(p.c,'command',call)
    with pytest.raises(p.c.Stop,match='owner_shell_required'):p.run(apply=True)
    call.assert_not_called()


def test_environment_dsn_blocks_owner_setup(monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS',raising=False)
    monkeypatch.setenv('DATABASE_URL','do-not-use')
    call=Mock();monkeypatch.setattr(p.c,'command',call)
    with pytest.raises(p.c.Stop,match='unset_shell'):p.run(apply=True)
    call.assert_not_called()


def test_pinned_enabled_version_is_preserved(monkeypatch):
    monkeypatch.setattr(p.c,'gc',lambda *a:[{'name':f'projects/{p.c.PROJECT}/secrets/{p.NAVER[0]}/versions/{i}','state':'ENABLED'} for i in (2,11)])
    assert p.secret_version(p.NAVER[0],'2')=='2'
    with pytest.raises(p.c.Stop):p.secret_version(p.NAVER[0],'1')


def test_foreign_secret_metadata_is_rejected(monkeypatch):
    monkeypatch.setattr(p.c,'gc',lambda *a:[{'name':f'projects/foreign/secrets/{p.NAVER[0]}/versions/2','state':'ENABLED'}])
    with pytest.raises(p.c.Stop):p.secret_version(p.NAVER[0])


@pytest.fixture
def setup_run(monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS',raising=False)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setattr(p.c,'source',lambda:'a'*40)
    def command(args,**kwargs):
        assert args==['git','remote','get-url','origin']
        return 'https://github.com/'+p.c.REPO+'.git'
    monkeypatch.setattr(p.c,'command',command)
    def gc(*args,**kwargs):
        if args==('auth','list','--filter=status:ACTIVE'):return [{'account':p.ACCOUNT}]
        if args==('projects','describe',p.c.PROJECT):return {'projectNumber':p.c.NUMBER}
        raise AssertionError('unexpected gcloud call')
    monkeypatch.setattr(p.c,'gc',gc)
    svc={'spec':{'template':{'spec':{'containers':[{'env':[{'name':'DATABASE_URL','valueFrom':{'secretKeyRef':{'name':'richon-portal-database-url','key':'1'}}}]}]}}}}
    monkeypatch.setattr(p,'service',lambda:(svc,{}))
    monkeypatch.setattr(p,'same_service',lambda *a:None)
    monkeypatch.setattr(p,'secret_version',lambda name,preferred=None:'1')
    monkeypatch.setattr(p,'secret_policy',lambda name:policy())
    # Synthetic DSNs only, validated against the real expected hostname without connecting.
    host='ep-gentle-night-b3h5xlji.c-4.ap-southeast-1.aws.neon.tech'
    monkeypatch.setattr(p,'secret_text',lambda name,v:'postgresql://'+('neondb_owner' if name==p.OWNER_SECRET else p.ready.ROLE)+':test-only@'+host+'/neondb?sslmode=verify-full')
    schema=Mock(return_value=False);monkeypatch.setattr(p,'check_schema',schema)
    restricted=Mock();monkeypatch.setattr(p,'restricted_check',restricted)
    migrate=Mock();monkeypatch.setattr(p.migration,'apply_migration',migrate)
    grant=Mock(return_value=True);monkeypatch.setattr(p,'ensure_grant',grant)
    return schema,restricted,migrate,grant


def test_read_only_is_default_and_never_prompts(setup_run,monkeypatch):
    ask=Mock(side_effect=AssertionError('should not prompt'));monkeypatch.setattr('builtins.input',ask)
    assert p.run()==0
    _,_,migrate,grant=setup_run
    migrate.assert_not_called();grant.assert_not_called();ask.assert_not_called()


def test_cancel_has_no_writes(setup_run,monkeypatch):
    monkeypatch.setattr('builtins.input',lambda _: 'CANCEL')
    assert p.run(apply=True)==0
    _,_,migrate,grant=setup_run;migrate.assert_not_called();grant.assert_not_called()


def test_approved_prerequisites_do_not_deploy_or_emit_secret(setup_run,monkeypatch,capsys):
    monkeypatch.setattr('builtins.input',lambda _:'PREPARE LOGIN')
    assert p.run(apply=True)==0
    _,restricted,migrate,grant=setup_run
    migrate.assert_called_once();restricted.assert_called_once();assert grant.call_count==2
    text=capsys.readouterr().out
    assert 'LOGIN PREREQUISITES READY' in text
    assert 'test-only' not in text and 'postgresql://' not in text
    assert p.REPORT['server_deployed'] is False and p.REPORT['database_008']=='verified'


def test_uncertain_migration_is_reported_not_automatically_reversed(setup_run,monkeypatch):
    monkeypatch.setattr('builtins.input',lambda _:'PREPARE LOGIN')
    _,_,migrate,grant=setup_run;migrate.side_effect=RuntimeError('private-error')
    with pytest.raises(RuntimeError):p.run(apply=True)
    assert p.REPORT['database_008']=='apply_attempted';grant.assert_not_called()


def test_failed_post_migration_check_blocks_grants(setup_run,monkeypatch):
    monkeypatch.setattr('builtins.input',lambda _:'PREPARE LOGIN')
    schema,_,_,grant=setup_run;schema.side_effect=[False,False,ValueError('invalid')]
    with pytest.raises(ValueError):p.run(apply=True)
    assert p.REPORT['database_008']=='apply_attempted';grant.assert_not_called()
