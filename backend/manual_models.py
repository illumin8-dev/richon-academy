"""Validated input for legacy records, not identity or PG verification."""
from datetime import date
import re
import unicodedata
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from monthly_store import month_start

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)

    @field_validator('*', mode='before')
    @classmethod
    def clean_text(cls, value):
        if isinstance(value, str):
            if any(unicodedata.category(c).startswith('C') for c in value):
                raise ValueError('invalid_text')
            return value.strip()
        return value

class Profile(Input):
    name: str = Field(min_length=1, max_length=80)
    nickname: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=24)
    original_joined_on: str | None = None

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        if not value: return None
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('invalid_email')
        return value

    @field_validator('phone')
    @classmethod
    def phone_format(cls, value):
        if not value: return None
        value = re.sub(r'[ ()-]', '', value)
        if value.startswith('+82'): value = '0' + value[3:]
        if not re.fullmatch(r'01[016789][0-9]{7,8}', value):
            raise ValueError('invalid_phone')
        return value

    @field_validator('original_joined_on')
    @classmethod
    def joined_date(cls, value):
        return calendar_day(value)


def calendar_day(value):
    if value in (None, ''): return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('invalid_day')
    return date.fromisoformat(value).isoformat()

class Write(Input):
    request_id: str
    reason: str = Field(min_length=2, max_length=200)

    @field_validator('request_id')
    @classmethod
    def uuid_text(cls, value):
        if str(UUID(value)) != value.lower(): raise ValueError('invalid_id')
        return value.lower()

class Term(Input):
    months: Literal[1,2,3,12]
    confirmed: bool = False
    quoted_amount_krw: int | None = Field(default=None, ge=0, le=100000000)
    payment_state: Literal['unknown','pending','recorded'] = 'unknown'
    paid_amount_krw: int | None = Field(default=None, ge=0, le=100000000)
    paid_on: str | None = None
    payment_ref: str | None = Field(default=None, max_length=200)
    receipt_state: Literal['unknown','not_requested','requested','recorded_issued'] = 'unknown'
    receipt_ref: str | None = Field(default=None, max_length=200)
    applied_on: str

    @field_validator('months', mode='before')
    @classmethod
    def integer_months(cls, value):
        if type(value) is not int: raise ValueError('invalid_months')
        return value

    @field_validator('applied_on','paid_on')
    @classmethod
    def day(cls, value): return calendar_day(value)

    @model_validator(mode='after')
    def consistency(self):
        if not self.applied_on: raise ValueError('application_day_required')
        if self.payment_state == 'recorded':
            if self.paid_amount_krw is None or not self.paid_on or not self.payment_ref:
                raise ValueError('payment_evidence_required')
        elif any(v is not None for v in (self.paid_amount_krw,self.paid_on,self.payment_ref)):
            raise ValueError('unexpected_payment_evidence')
        if self.confirmed and self.payment_state == 'pending':
            raise ValueError('pending_payment_cannot_confirm')
        if self.receipt_state != 'recorded_issued' and self.receipt_ref is not None:
            raise ValueError('unexpected_receipt_evidence')
        if self.receipt_state == 'recorded_issued' and not self.receipt_ref:
            raise ValueError('receipt_evidence_required')
        return self

class Create(Write):
    course_id: str = Field(min_length=1, max_length=64, pattern=r'^[a-z0-9][a-z0-9_-]*$')
    profile: Profile | None = None
    existing_learner_id: str | None = None
    learner_version: int | None = Field(default=None, ge=1)
    term: Term

    @model_validator(mode='after')
    def one_identity(self):
        if self.existing_learner_id:
            Write.uuid_text(self.existing_learner_id)
            if self.profile is not None or self.learner_version is None:
                raise ValueError('explicit_existing_learner_required')
        elif self.profile is None or self.learner_version is not None:
            raise ValueError('new_profile_required')
        return self

class Target(Write):
    enrollment_id: str
    version: int = Field(ge=1)
    _id = field_validator('enrollment_id')(Write.uuid_text.__func__)

class Update(Target):
    learner_version: int = Field(ge=1)
    profile: Profile

class AddTerm(Target):
    term: Term

class EditTerm(AddTerm):
    term_id: str
    _term_id = field_validator('term_id')(Write.uuid_text.__func__)

class Archive(Target):
    archived: bool

class Read(Input):
    enrollment_id: str
    _id = field_validator('enrollment_id')(Write.uuid_text.__func__)

class Search(Input):
    q: str = Field(default='', max_length=200)
    archived: bool = False
    month: str | None = None
    course_id: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)

    @field_validator('month')
    @classmethod
    def month_format(cls, value):
        if value: month_start(value)
        return value or None

class Course(Write):
    title: str = Field(min_length=1, max_length=200)
    cohort: str | None = Field(default=None, max_length=100)
    start_month: str
    duration_kind: Literal['monthly','fixed']
    price_krw: int = Field(ge=1, le=100000000)

    @field_validator('start_month')
    @classmethod
    def start(cls, value):
        month_start(value)
        return value
