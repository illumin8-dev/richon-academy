"""Pure validation for the new course catalog."""
from uuid import uuid4
import pytest
from pydantic import ValidationError
import catalog_models as m

def write():
    return {'request_id':str(uuid4()),'reason':'가상 테스트'}

def test_program_access_policies():
    fixed=m.ProgramCreate(**write(),title='프리리치온',access_kind='fixed_months',fixed_months=2)
    assert fixed.fixed_months==2
    ranged=m.ProgramCreate(**write(),title='리치온',access_kind='date_range')
    assert ranged.fixed_months is None
    with pytest.raises(ValidationError):
        m.ProgramCreate(**write(),title='잘못된 고정형',access_kind='fixed_months')
    with pytest.raises(ValidationError):
        m.ProgramCreate(**write(),title='잘못된 기간형',access_kind='date_range',fixed_months=3)

def test_run_dates_and_statuses_are_bounded():
    body={**write(),'program_id':str(uuid4()),'status':'OPEN','starts_on':'2026-10-01','ends_on':'2026-11-30',
          'default_access_start':'2026-10-01','default_access_end':'2026-11-30','capacity':40,'price_krw':1000}
    assert m.RunCreate.model_validate_json(__import__('json').dumps(body)).status=='OPEN'
    with pytest.raises(ValidationError):
        m.RunCreate.model_validate_json(__import__('json').dumps({**body,'status':'PAID'}))
    with pytest.raises(ValidationError):
        m.RunCreate.model_validate_json(__import__('json').dumps({**body,'ends_on':'2026-09-30'}))

def test_session_requires_aware_time_and_https_content():
    base={**write(),'run_id':str(uuid4()),'sequence_no':1,'title':'시장 흐름',
          'mentor_name':'이루민','starts_at':'2026-10-07T20:00:00+09:00',
          'ends_at':'2026-10-07T22:00:00+09:00','content_url':'https://example.invalid/video'}
    assert m.SessionCreate.model_validate_json(__import__('json').dumps(base)).mentor_name=='이루민'
    with pytest.raises(ValidationError):
        m.SessionCreate.model_validate_json(__import__('json').dumps({**base,'content_url':'http://example.invalid'}))
    with pytest.raises(ValidationError):
        m.SessionCreate.model_validate_json(__import__('json').dumps({**base,'ends_at':'2026-10-07T19:00:00+09:00'}))
