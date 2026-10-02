"""Legacy roster import contracts; no customer database access."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('legacy_roster_import',ROOT/'ops'/'import_legacy_roster.py')
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
SQL=(ROOT/'backend'/'migrations'/'020_legacy_roster_import.sql').read_text()
SOURCE=(ROOT/'ops'/'import_legacy_roster.py').read_text()


def payload():
    learner=str(uuid4())
    return {
        'schema_version':1,
        'source_name':'synthetic.xlsx',
        'source_sha256':'a'*64,
        'batch_id':str(uuid4()),
        'corrections':[],
        'learners':[{
            'learner_id':learner,'name':'홍길동','nickname':'길동',
            'email':'test@example.com','phone':'01012345678','source_count':1,
        }],
        'rows':[{
            'legacy_row_id':str(uuid4()),'learner_id':learner,
            'source_sheet':'sheet','source_row':2,'course_label':'리치온',
            'purchase_months':6,'amount_krw':495000,'payer_name':'홍길동',
            'email_snapshot':'test@example.com','contact_snapshot':'010-1234-5678',
            'nickname_snapshot':'길동','joined_on':'2026-04-01','ended_on':'2026-10-31',
            'receipt_issued':True,'raw_record':{'course':'리치온'},
        }],
        'canonical':{'enrollments':[{
            'kind':'richon','learner_id':learner,'access_start':'2026-04-01',
            'access_end':'2026-10-31','status':'ACTIVE','source_sheet':'sheet','source_row':2,
        }]},
    }


def test_payload_accepts_actual_richon_six_month_shape():
    assert mod.validate_payload(payload())['rows'][0]['purchase_months']==6


def test_payload_rejects_reversed_dates():
    data=deepcopy(payload())
    data['rows'][0]['ended_on']='2026-03-31'
    with pytest.raises(mod.Stop,match='invalid_access_window'):
        mod.validate_payload(data)


def test_payload_rejects_duplicate_source_position():
    data=deepcopy(payload())
    other=deepcopy(data['rows'][0])
    other['legacy_row_id']=str(uuid4())
    data['rows'].append(other)
    with pytest.raises(mod.Stop,match='duplicate_source_position'):
        mod.validate_payload(data)


def test_schema_is_owner_only_ledger_and_preserves_raw_record():
    assert 'CREATE TABLE richon.legacy_roster_imports' in SQL
    assert 'CREATE TABLE richon.legacy_roster_rows' in SQL
    assert 'raw_record jsonb NOT NULL' in SQL
    assert 'REVOKE ALL ON richon.legacy_roster_imports, richon.legacy_roster_rows FROM PUBLIC' in SQL


def test_importer_never_creates_members_or_auth_identities():
    assert 'INSERT INTO richon.members' not in SOURCE
    assert 'INSERT INTO richon.auth_identities' not in SOURCE
    assert "MEMBERS_CREATED=0 / AUTH_IDENTITIES_CREATED=0" in SOURCE


def test_enrollment_ids_are_deterministic():
    run=str(uuid4()); learner=str(uuid4())
    assert mod.enrollment_id(run,learner)==mod.enrollment_id(run,learner)
