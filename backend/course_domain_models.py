"""Validated canonical course/run/session/enrollment inputs."""
from datetime import date, datetime
import re
import unicodedata
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RunStatus=Literal['OPEN','WAITLIST','UPCOMING','CLOSED']

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)

    @field_validator(
        'reason','program_id','title','description','access_mode','cohort_label','status',
        'mentor_name','video_url','material_url','name','email','phone','note',
        mode='before',check_fields=False)
    @classmethod
    def clean_text(cls,value):
        if isinstance(value,str):
            if any(unicodedata.category(c).startswith('C') for c in value):
                raise ValueError('invalid_text')
            return value.strip()
        return value

class Write(Input):
    request_id: UUID
    reason: str=Field(min_length=2,max_length=200)

class ProgramCreate(Write):
    program_id: str=Field(min_length=1,max_length=64,pattern=r'^[a-z0-9][a-z0-9_-]*$')
    title: str=Field(min_length=1,max_length=200)
    description: str|None=Field(default=None,max_length=500)
    access_mode: Literal['fixed_months','date_range']
    fixed_months: int|None=Field(default=None,ge=1,le=36)
    @model_validator(mode='after')
    def access(self):
        if (self.access_mode=='fixed_months') != (self.fixed_months is not None):
            raise ValueError('invalid_access_model')
        return self

class ProgramUpdate(Write):
    program_id: str=Field(min_length=1,max_length=64,pattern=r'^[a-z0-9][a-z0-9_-]*$')
    version: int=Field(ge=1)
    title: str=Field(min_length=1,max_length=200)
    description: str|None=Field(default=None,max_length=500)
    archived: bool=False

class RunCreate(Write):
    program_id: str=Field(min_length=1,max_length=64,pattern=r'^[a-z0-9][a-z0-9_-]*$')
    cohort_label: str|None=Field(default=None,max_length=100)
    starts_on: date
    ends_on: date
    default_access_start: date
    default_access_end: date
    recruit_opens_at: datetime|None=None
    recruit_closes_at: datetime|None=None
    capacity: int|None=Field(default=None,ge=1,le=100000)
    status: RunStatus
    price_krw: int=Field(default=0,ge=0,le=100000000)
    @model_validator(mode='after')
    def dates(self):
        if self.ends_on<self.starts_on or self.default_access_end<self.default_access_start:
            raise ValueError('invalid_date_range')
        if self.recruit_opens_at and self.recruit_closes_at and self.recruit_closes_at<self.recruit_opens_at:
            raise ValueError('invalid_recruit_range')
        return self

class RunUpdate(Write):
    run_id: UUID
    version: int=Field(ge=1)
    cohort_label: str|None=Field(default=None,max_length=100)
    recruit_opens_at: datetime|None=None
    recruit_closes_at: datetime|None=None
    capacity: int|None=Field(default=None,ge=1,le=100000)
    status: RunStatus
    price_krw: int=Field(default=0,ge=0,le=100000000)
    archived: bool=False
    @model_validator(mode='after')
    def recruit(self):
        if self.recruit_opens_at and self.recruit_closes_at and self.recruit_closes_at<self.recruit_opens_at:
            raise ValueError('invalid_recruit_range')
        return self

class SessionCreate(Write):
    run_id: UUID
    sequence_no: int=Field(ge=1,le=1000)
    title: str=Field(min_length=1,max_length=200)
    mentor_name: str|None=Field(default=None,max_length=80)
    starts_at: datetime
    ends_at: datetime|None=None
    video_url: str|None=Field(default=None,max_length=2048)
    material_url: str|None=Field(default=None,max_length=2048)
    @field_validator('video_url','material_url')
    @classmethod
    def https(cls,value):
        if value and not value.startswith('https://'): raise ValueError('https_required')
        return value
    @model_validator(mode='after')
    def time(self):
        if self.ends_at and self.ends_at<=self.starts_at: raise ValueError('invalid_session_range')
        return self

class TargetProfile(Input):
    name: str=Field(min_length=1,max_length=80)
    email: str|None=Field(default=None,max_length=254)
    phone: str|None=Field(default=None,max_length=24)
    @field_validator('email')
    @classmethod
    def email_format(cls,value):
        if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value): raise ValueError('invalid_email')
        return value
    @field_validator('phone')
    @classmethod
    def phone_format(cls,value):
        if not value:return None
        value=re.sub(r'[ ()-]','',value)
        if value.startswith('+82'):value='0'+value[3:]
        if not re.fullmatch(r'01[016789][0-9]{7,8}',value):raise ValueError('invalid_phone')
        return value

class EnrollmentGrant(Write):
    run_id: UUID
    member_id: UUID|None=None
    learner_id: UUID|None=None
    profile: TargetProfile|None=None
    access_start: date|None=None
    access_end: date|None=None
    note: str|None=Field(default=None,max_length=500)
    @model_validator(mode='after')
    def target_and_dates(self):
        if sum(x is not None for x in (self.member_id,self.learner_id,self.profile))!=1:
            raise ValueError('one_target_required')
        if (self.access_start is None)!=(self.access_end is None):
            raise ValueError('complete_access_range_required')
        if self.access_start and self.access_end and self.access_end<self.access_start:
            raise ValueError('invalid_access_range')
        return self

class EnrollmentCancel(Write):
    enrollment_id: UUID
    version: int=Field(ge=1)
