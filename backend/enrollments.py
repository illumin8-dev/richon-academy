"""Staged calendar-month enrollment reads. No payment or enrollment writes."""
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo
import logging
import os
import unicodedata

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from auth_core import Principal
from auth_http import require_admin, require_member
from portal import PAGE_HEADERS, HEADERS
import enrollment_store as store

logger = logging.getLogger('richon.enrollments')
STATIC = Path(__file__).parent / 'enrollment_static'
State = Literal['pending','scheduled','active','ended','cancelled','needs_review']


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    q: str = Field(default='',max_length=200)
    course_id: str | None = Field(default=None,max_length=64,pattern=r'^[a-z0-9][a-z0-9_-]*$')
    cohort: str | None = Field(default=None,max_length=80)
    months: Literal[1,3,12] | None = None
    status: State | None = None
    end_from: date | None = None
    end_to: date | None = None
    receipt: Literal['requested','not_requested','unknown'] | None = None
    sort: Literal['ending','newest','name'] = 'ending'
    limit: int = Field(default=20,ge=1,le=50)
    offset: int = Field(default=0,ge=0,le=10000)

    @field_validator('q','cohort')
    @classmethod
    def text(cls,value):
        if value is None:
            return value
        if any(unicodedata.category(c).startswith('C') for c in value):
            raise ValueError('invalid_filter')
        return value.strip()

    @field_validator('months',mode='before')
    @classmethod
    def months_from_query(cls,value):
        # Query values are strings; reject bools/non-integral numbers.
        if value is None:
            return None
        if type(value) is int and value in (1,3,12):
            return value
        if type(value) is str and value in ('1','3','12'):
            return int(value)
        raise ValueError('invalid_months')

    @model_validator(mode='after')
    def date_range(self):
        if self.end_from and self.end_to and self.end_from > self.end_to:
            raise ValueError('invalid_date_range')
        return self


class EnrollmentItem(BaseModel):
    enrollment_id: UUID
    learner_id: UUID
    member_id: UUID | None
    full_name: str
    nickname: str | None
    email_masked: str | None
    phone_masked: str | None
    course_id: str
    course_title: str
    cohort: str | None
    joined_at: datetime | None
    applied_at: datetime
    starts_on: date
    ends_on: date | None
    remaining_days: int | None
    enrollment_status: State
    calendar_review_required: bool
    latest_plan_months: Literal[1,3,12] | None
    total_months: int
    confirmed_term_count: int
    pending_term_count: int
    latest_agreed_amount_krw: int | None
    latest_discount_krw: int | None
    agreed_total_krw: int
    cash_receipt_requested: bool | None
    latest_term_status: Literal['pending','confirmed'] | None
    paid_amount_krw: None = None
    payment_status: Literal['not_connected']
    cash_receipt_status: Literal['unverified']


class Counts(BaseModel):
    enrollment_count: int
    learner_count: int
    active_learners: int
    scheduled_enrollments: int
    ending_soon: int
    pending_enrollments: int
    needs_review: int


class CourseCount(BaseModel):
    course_id: str
    course_title: str
    cohort: str | None
    active_learners: int
    scheduled_enrollments: int
    matching_enrollments: int


class Overview(BaseModel):
    as_of: date
    summary: Counts
    items: list[EnrollmentItem]
    courses: list[CourseCount]
    courses_truncated: bool
    limit: int
    offset: int
    has_more: bool


def get_overview(response, params, *, member_id=None):
    response.headers.update(HEADERS)
    try:
        # Validate before returning so missing schema/corrupt rows become safe 503.
        return Overview.model_validate(store.overview(
            params, datetime.now(ZoneInfo('Asia/Seoul')).date(),member_id=member_id))
    except Exception:
        logger.warning('enrollment_store_unavailable')
        raise HTTPException(503,'enrollment_store_unavailable',headers=HEADERS) from None


def make_router():
    router = APIRouter(prefix='/portal/api')

    @router.get('/admin/enrollments',response_model=Overview)
    def admin_enrollments(response: Response,
                          admin: Annotated[Principal,Depends(require_admin)],
                          params: Annotated[Filters,Query()]):
        return get_overview(response,params)

    @router.get('/me/enrollments',response_model=Overview)
    def my_enrollments(response: Response,
                       member: Annotated[Principal,Depends(require_member)],
                       params: Annotated[Filters,Query()]):
        return get_overview(response,params,member_id=member.member_id)
    return router


def install_if_enabled(app: FastAPI) -> bool:
    if os.getenv('RICHON_ENROLLMENTS_ENABLED','false') != 'true':
        return False
    if (os.getenv('RICHON_PORTAL_ENABLED') != 'true'
            or not any(getattr(r,'path',None)=='/portal/api/me' for r in app.routes)):
        raise ValueError('enrollments_require_portal')
    app.include_router(make_router())

    @app.get('/portal/admin/enrollments',include_in_schema=False)
    def page():
        return FileResponse(STATIC / 'enrollments.html',headers=PAGE_HEADERS)

    @app.get('/portal/enrollments/assets/{asset}',include_in_schema=False)
    def asset(asset: str):
        if asset not in {'enrollments.css','enrollments.js'}:
            raise HTTPException(404,'not_found',headers=HEADERS)
        return FileResponse(STATIC / asset,headers=HEADERS)
    return True
