"""Bootstrap guards: no cloud calls or database credentials in these tests."""
import importlib.util
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ops'))
import prepare_portal as p
import portal_readiness as ready

OWNER = 'postgresql://neondb_owner:synthetic@ep-gentle-night-b3h5xlji.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'


def test_scoped_url_keeps_known_target():
    value=p.runtime_url(OWNER,'synthetic-password')
    u=p.validate_dsn(value,ready.ROLE)
    assert u.username==ready.ROLE and u.path=='/neondb'
    assert 'neondb_owner:' not in value


@pytest.mark.parametrize('value',[
    OWNER.replace('ep-gentle-night-b3h5xlji','ep-other'),
    OWNER.replace('/neondb?','/other?'),
    OWNER.replace('neondb_owner:','different:'),
    OWNER+'&options=-csearch_path%3Dpublic',
    OWNER+'#fragment', OWNER+' ',
    OWNER.replace('.neon.tech','.neon.tech.attacker.invalid'),
])
def test_other_database_targets_rejected(value):
    with pytest.raises((p.Stop,ValueError)):
        p.validate_dsn(value,'neondb_owner')


@pytest.mark.parametrize('member',['allUsers','allAuthenticatedUsers'])
def test_public_service_rejected(member):
    with pytest.raises(p.Stop,match='public_iam'):
        p.private({'bindings':[{'members':[member]}]},{})


def test_disabled_iam_check_rejected():
    with pytest.raises(p.Stop,match='iam_check'):
        p.private({}, {'metadata':{'annotations':{'run.googleapis.com/invoker-iam-disabled':'true'}}})


def test_active_or_unmanaged_service_not_overwritten():
    service={'metadata':{'labels':{'managed-by':p.MARKER}},'spec':{'template':{'spec':{'serviceAccountName':p.RUNTIME,'containers':[{'env':[{'name':k,'value':v} for k,v in p.OFF.items()]}]}}}}
    p.validate_existing(service,{})
    service['spec']['template']['spec']['containers'][0]['env'][0]['value']='true'
    with pytest.raises(p.Stop,match='active_portal'):
        p.validate_existing(service,{})
    service['metadata']['labels']={}
    with pytest.raises(p.Stop,match='unmanaged_portal'):
        p.validate_existing(service,{})


def test_subprocess_error_does_not_leak_secrets(monkeypatch):
    monkeypatch.setattr(p.subprocess,'run',Mock(return_value=type('R',(),{'returncode':1,'stdout':b'PRIVATE','stderr':b'postgresql://PRIVATE'})()))
    with pytest.raises(p.Stop) as exc:
        p.command(['gcloud','unused'])
    assert str(exc.value)=='command_failed'


def test_readiness_disabled_never_connects(monkeypatch):
    monkeypatch.delenv('RICHON_BOOTSTRAP_VERIFY',raising=False)
    database=Mock(side_effect=AssertionError('must not connect'));monkeypatch.setattr(ready,'verify_database',database)
    fake=Mock();monkeypatch.setitem(sys.modules,'uvicorn',fake)
    assert ready.main()==0
    database.assert_not_called()
    assert fake.run.call_args.kwargs['access_log'] is False
    assert fake.run.call_args.kwargs['proxy_headers'] is False


def test_failed_startup_never_listens_or_logs_exception(monkeypatch,capsys):
    monkeypatch.setenv('RICHON_BOOTSTRAP_VERIFY','true')
    monkeypatch.setattr(ready,'verify_database',Mock(side_effect=RuntimeError('SECRET-DSN')))
    fake=Mock();monkeypatch.setitem(sys.modules,'uvicorn',fake)
    assert ready.main()==1
    fake.run.assert_not_called()
    output=capsys.readouterr()
    assert 'SECRET' not in output.err+output.out
    assert 'PORTAL_DATABASE_CHECK_FAILED' in output.err


def test_bootstrap_preserves_disabled_public_boundary():
    assert set(p.OFF.values())=={'false'}
    assert p.SERVICE!='richon-backend-test'
    assert p.MIGRATIONS==('001_pending_orders','002_auth_foundation','003_portal_read_models','007_oauth_handoff')
    assert 'role' not in ready.INSERT['members'] and 'role' not in ready.UPDATE['members']
