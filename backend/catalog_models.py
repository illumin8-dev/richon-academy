"""Validated admin inputs for the new course catalog; no payment operations."""
import re
import unicodedata
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

RunStatus=Literal['UPCOMING','OPEN','WAITLIST','CLOSED']
AccessKind=Literal['fixed_months','date_range']

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    @field_validator('*',mode='before')
    @classmethod
    def clean_text(cls,value):
        if isinstance(value,str):
            if any(unicodedata.category(c).startswith('C') for c in value):
                raise ValueError('invalid_text')
            return value.strip()
        return value

class Write(Input):
    request_id:str
    reason:str=Field(min_length=2,max_length=200)
    @field_validator('request_id')
    @classmethod
    def uuid_text(cls,value):
        if str(UUID(value))!=value.lower(): raise ValueError('invalid_id')
        return value.lower()

def uuid_text(value):
    if str(UUID(value))!=value.lower(): raise ValueError('invalid_id')
    return value.lower()

class ProgramCreate(Write):
    title:str=Field(min_length=1,max_length=200)
    description:str|None=Field(default=None,max_length=1200)
    access_kind:AccessKind
    fixed_months:int|None=Field(default=None,ge=1,le=24)
    @model_validator(mode='after')
    def policy(self):
        if self.access_kind=='fixed_months' and self.fixed_months is None:
            raise ValueError('fixed_months_required')
        if self.access_kind=='date_range' and self.fixed_months is not None:
            raise ValueError('fixed_months_not_allowed')
        return self

class ProgramUpdate(ProgramCreate):
    program_id:str
    version:int=Field(ge=1)
    archived:bool=False
    _program_id=field_validator('program_id')(uuid_text)

class RunBase(Input):
    cohort:str|None=Field(default=None,max_length=100)
    status:RunStatus
    starts_on:date
    ends_on:date
    default_access_start:date|None=None
    default_access_end:date|None=None
    recruitment_open_at:AwareDatetime|None=None
    recruitment_close_at:AwareDatetime|None=None
    capacity:int|None=Field(default=None,ge=1,le=100000)
    price_krw:int=Field(default=0,ge=0,le=100000000)
    @model_validator(mode='after')
    def chronology(self):
        if self.ends_on<self.starts_on: raise ValueError('invalid_run_dates')
        if (self.default_access_start is None)!=(self.default_access_end is None):
            raise ValueError('access_period_pair_required')
        if self.default_access_start and self.default_access_end<self.default_access_start:
            raise ValueError('invalid_access_period')
        if self.recruitment_open_at and self.recruitment_close_at and self.recruitment_close_at<self.recruitment_open_at:
            raise ValueError('invalid_recruitment_period')
        return self

class RunCreate(Write,RunBase):
    program_id:str
    _program_id=field_validator('program_id')(uuid_text)

class RunUpdate(Write,RunBase):
    run_id:str
    version:int=Field(ge=1)
    archived:bool=False
    _run_id=field_validator('run_id')(uuid_text)

class SessionBase(Input):
    sequence_no:int=Field(ge=1,le=1000)
    title:str=Field(min_length=1,max_length=200)
    mentor_name:str|None=Field(default=None,max_length=80)
    starts_at:AwareDatetime
    ends_at:AwareDatetime|None=None
    content_url:str|None=Field(default=None,max_length=2048)
    @model_validator(mode='after')
    def consistency(self):
        if self.ends_at and self.ends_at<=self.starts_at: raise ValueError('invalid_session_time')
        if self.content_url and not re.fullmatch(r'https://[^\s]+',self.content_url):
            raise ValueError('invalid_content_url')
        return self

class SessionCreate(Write,SessionBase):
    run_id:str
    _run_id=field_validator('run_id')(uuid_text)

class SessionUpdate(Write,SessionBase):
    session_id:str
    version:int=Field(ge=1)
    archived:bool=False
    _session_id=field_validator('session_id')(uuid_text)
