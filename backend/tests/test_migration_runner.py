"""Synthetic tests for the shared standard migration execution engine."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from migration_runner import apply_standard_migration


import marketing_consent_migrate
import oauth_signup_profile_migrate
import oauth_signup_demographics_migrate

import kakao_ci_migrate
import course_entitlement_migrate

import account_migrate
import course_domain_migrate
import calendar_migrate
import calendar_freeform_migrate
import monthly_runtime_hardening_migrate

class Context:
    def __init__(self,value):
        self.value=value

    def __enter__(self):
        return self.value

    def __exit__(self,*_):
        return False


class Cursor:
    def __init__(self,rows):
        self.rows=list(rows)
        self.executed=[]

    def __enter__(self):
        return self

    def __exit__(self,*_):
        return False

    def execute(self,sql,params=None):
        self.executed.append((sql,params))

    def fetchone(self):
        return self.rows.pop(0)


def target(tmp_path,rows):
    directory=tmp_path/'migrations'
    directory.mkdir()
    for name,text in [('dep','dep-sql'),('target','target-sql')]:
        (directory/(name+'.sql')).write_text(text)
    cur=Cursor(rows)
    conn=SimpleNamespace(cursor=lambda:Context(cur))
    db=SimpleNamespace(
        database_url=lambda:'synthetic://default',
        _connect=MagicMock(return_value=Context(conn)),
    )
    checksum=lambda name:'checksum-'+name
    return directory,cur,db,checksum


def apply(directory,db,checksum,**kwargs):
    return apply_standard_migration(
        db_module=db,
        directory=directory,
        version='target',
        dependencies=('dep',),
        checksum=checksum,
        **kwargs,
    )


def test_applies_new_migration_and_uses_explicit_connection_url(tmp_path):
    directory,cur,db,checksum=target(tmp_path,[('checksum-dep',),None])
    assert apply(directory,db,checksum,connection_url='synthetic://override') is True
    db._connect.assert_called_once_with('synthetic://override')
    assert cur.executed[:3]==[
        ("SET LOCAL statement_timeout='15s'",None),
        ("SET LOCAL lock_timeout='10s'",None),
        ('SELECT pg_advisory_xact_lock(726426,1)',None),
    ]
    assert ('target-sql',None) in cur.executed
    assert cur.executed[-1][1]==('target','checksum-target')


def test_statement_timeout_can_be_overridden(tmp_path):
    directory,cur,db,checksum=target(tmp_path,[('checksum-dep',),None])
    assert apply(directory,db,checksum,statement_timeout_seconds=20) is True
    assert cur.executed[0]==("SET LOCAL statement_timeout='20s'",None)


def test_advisory_lock_slot_can_be_overridden(tmp_path):
    directory,cur,db,checksum=target(tmp_path,[('checksum-dep',),None])
    assert apply(directory,db,checksum,advisory_slot=2) is True
    assert cur.executed[2]==('SELECT pg_advisory_xact_lock(726426,2)',None)


def test_existing_matching_migration_is_idempotent(tmp_path):
    directory,cur,db,checksum=target(tmp_path,[('checksum-dep',),('checksum-target',)])
    assert apply(directory,db,checksum) is False
    db._connect.assert_called_once_with('synthetic://default')
    assert ('target-sql',None) not in cur.executed


@pytest.mark.parametrize(
    ('rows','message'),
    [
        ([(None,),None],'dependency_mismatch'),
        ([('checksum-dep',),('wrong',)],'migration_mismatch'),
    ],
)
def test_rejects_ledger_mismatch(tmp_path,rows,message):
    directory,cur,db,checksum=target(tmp_path,rows)
    with pytest.raises(ValueError,match=message):
        apply(directory,db,checksum)
    assert ('target-sql',None) not in cur.executed


def test_dependency_error_can_include_version(tmp_path):
    directory,cur,db,checksum=target(tmp_path,[(None,)])
    with pytest.raises(ValueError,match='dependency_mismatch_dep'):
        apply(directory,db,checksum,dependency_error_with_version=True)
    assert ('target-sql',None) not in cur.executed


@pytest.mark.parametrize(
    'module',
    [
        marketing_consent_migrate,
        oauth_signup_profile_migrate,
        oauth_signup_demographics_migrate,
    ],
)
def test_pilot_migration_modules_delegate_to_standard_runner(monkeypatch,module):
    called={}

    def fake_runner(**kwargs):
        called.update(kwargs)
        return 'sentinel'

    monkeypatch.setattr(module,'apply_standard_migration',fake_runner)
    assert module.apply_migration(connection_url='synthetic://override')=='sentinel'
    assert called=={
        'db_module':module.db,
        'directory':module.DIRECTORY,
        'version':module.VERSION,
        'dependencies':module.DEPENDENCIES,
        'checksum':module.checksum,
        'connection_url':'synthetic://override',
    }


@pytest.mark.parametrize(
    ('module','extra'),
    [
        (kakao_ci_migrate,{}),
        (course_entitlement_migrate,{'advisory_slot':2}),
    ],
)
def test_lock_slot_migration_modules_delegate_to_standard_runner(monkeypatch,module,extra):
    called={}

    def fake_runner(**kwargs):
        called.update(kwargs)
        return 'sentinel'

    monkeypatch.setattr(module,'apply_standard_migration',fake_runner)
    assert module.apply_migration(connection_url='synthetic://override')=='sentinel'
    expected={
        'db_module':module.db,
        'directory':module.DIRECTORY,
        'version':module.VERSION,
        'dependencies':module.DEPENDENCIES,
        'checksum':module.checksum,
        'connection_url':'synthetic://override',
    }
    expected.update(extra)
    assert called==expected



@pytest.mark.parametrize(
    ('module','extra'),
    [
        (course_domain_migrate,{'dependency_error_with_version':True}),
        (calendar_migrate,{'advisory_slot':4,'dependency_error_with_version':True}),
        (calendar_freeform_migrate,{'advisory_slot':5,'dependency_error_with_version':True}),
        (monthly_runtime_hardening_migrate,{'advisory_slot':5,'dependency_error_with_version':True}),
    ],
)
def test_versioned_dependency_migrations_delegate_to_standard_runner(monkeypatch,module,extra):
    called={}

    def fake_runner(**kwargs):
        called.update(kwargs)
        return 'sentinel'

    monkeypatch.setattr(module,'apply_standard_migration',fake_runner)
    assert module.apply_migration(connection_url='synthetic://override')=='sentinel'
    expected={
        'db_module':module.db,
        'directory':module.DIRECTORY,
        'version':module.VERSION,
        'dependencies':module.DEPENDENCIES,
        'checksum':module.checksum,
        'connection_url':'synthetic://override',
    }
    expected.update(extra)
    assert called==expected

def test_account_migration_delegates_timeout_override(monkeypatch):
    called={}

    def fake_runner(**kwargs):
        called.update(kwargs)
        return 'sentinel'

    monkeypatch.setattr(account_migrate,'apply_standard_migration',fake_runner)
    assert account_migrate.apply_migration(connection_url='synthetic://override')=='sentinel'
    assert called=={
        'db_module':account_migrate.db,
        'directory':account_migrate.DIRECTORY,
        'version':account_migrate.VERSION,
        'dependencies':account_migrate.DEPENDENCIES,
        'checksum':account_migrate.checksum,
        'connection_url':'synthetic://override',
        'statement_timeout_seconds':20,
    }
