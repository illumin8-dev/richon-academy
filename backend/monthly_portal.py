"""Admin-only monthly enrollment search. Default OFF. POST search is read-only."""
from datetime import datetime
import logging
import os
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from auth_core import Principal
from auth_http import require_admin, AuthSettings, _origin, _csrf, cookie_token
from portal import PAGE_HEADERS, HEADERS, SearchQuery, PageQuery, PageResult
import monthly_store as store

logger = logging.getLogger('richon.monthly')
STATIC = Path(__file__).parent / 'portal_static'
PAYMENT = Literal['unknown','pending','recorded','refunded']
RECEIPT = Literal['unknown','not_requested','requested','recorded_issued']


class Filters(SearchQuery):
    model_config = ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    month: str
    scope: Literal['month','all'] = 'month'
    course_id: str | None = Field(default=None,min_length=1,max_length=64,pattern=r'^[a-z0-9][a-z0-9_-]*$')
    plan_months: Literal[1,2,3,12] | None = None
    status: Literal['scheduled','active','ended','pending','ending'] | None = None
    payment_state: PAYMENT | None = None
    receipt_state: RECEIPT | None = None
    member_linked: bool | None = None
    end_from: str | None = None
    end_to: str | None = None

    @field_validator('month','end_from','end_to')
    @classmethod
    def valid_month(cls,value):
        if value is not None: store.month_start(value)
        return value

    @field_validator('plan_months',mode='before')
    @classmethod
    def valid_plan(cls,value):
        if value is not None and type(value) is not int: raise ValueError('invalid_plan')
        return value

    @model_validator(mode='after')
    def ordered_range(self):
        if self.end_from and self.end_to and self.end_from>self.end_to:
            raise ValueError('invalid_end_range')
        return self


class EnrollmentRow(BaseModel):
    enrollment_id: UUID
    learner_id: UUID
    course_id: str
    course_title: str
    cohort: str | None
    name: str
    nickname: str | None
    phone_masked: str | None
    email_masked: str | None
    member_linked: bool
    joined_at: datetime | None
    start_month: str
    end_month: str | None
    duration_kind: Literal['monthly','fixed']
    confirmed_months: int
    pending_terms: int
    term_count: int
    status: Literal['scheduled','active','ended','pending']
    last_plan_months: int | None
    last_applied_at: datetime | None
    latest_quoted_krw: int | None
    net_recorded_paid_krw: int | None
    refunded_krw: int
    latest_payment_state: PAYMENT | None
    latest_receipt_state: RECEIPT | None


class MonthSummary(BaseModel):
    total: int
    confirmed_people: int
    confirmed_enrollments: int
    starting_people: int
    ending_people: int
    pending_people: int


class CourseCount(BaseModel):
    course_id: str
    course_title: str
    cohort: str | None
    confirmed_people: int
    pending_people: int


class SearchResult(BaseModel):
    month: str
    summary: MonthSummary
    courses: list[CourseCount]
    courses_truncated: bool
    items: list[EnrollmentRow]
    limit: int
    offset: int
    has_more: bool


class TermRow(BaseModel):
    term_id: UUID
    sequence_no: int
    months: int
    grant_state: Literal['pending','confirmed','cancelled']
    order_id: str | None
    applied_at: datetime
    start_month: str | None
    end_month: str | None
    quoted_amount_krw: int | None
    payment_state: PAYMENT
    paid_amount_krw: int | None
    refunded_amount_krw: int
    paid_at: datetime | None
    receipt_state: RECEIPT


def read(response,operation,*args):
    response.headers.update(HEADERS)
    try: return operation(*args)
    except store.MissingEnrollment:
        raise HTTPException(404,'enrollment_not_found',headers=HEADERS) from None
    except Exception:
        logger.warning('monthly_store_unavailable')
        raise HTTPException(503,'monthly_store_unavailable',headers=HEADERS) from None


def make_router(settings: AuthSettings) -> APIRouter:
    router = APIRouter(prefix='/portal/api/admin/enrollments')

    @router.get('/options')
    def options(response: Response,admin: Annotated[Principal,Depends(require_admin)]):
        return read(response,store.options)

    @router.post('/search',response_model=SearchResult)
    def search(request: Request,response: Response,admin: Annotated[Principal,Depends(require_admin)],
               filters: Annotated[Filters,Body()]):
        _origin(request,settings)
        _csrf(request,cookie_token(request))
        return read(response,store.search,filters)

    @router.get('/{enrollment_id}/terms',response_model=PageResult[TermRow])
    def terms(enrollment_id: UUID,response: Response,admin: Annotated[Principal,Depends(require_admin)],
              params: Annotated[PageQuery,Query()]):
        return read(response,store.history,enrollment_id,params.limit,params.offset)

    return router


def install_if_enabled(app: FastAPI) -> bool:
    if os.getenv('RICHON_MONTHLY_ENABLED','false')!='true': return False
    if (os.getenv('RICHON_AUTH_ENABLED')!='true' or os.getenv('RICHON_PORTAL_ENABLED')!='true'
        or not any(getattr(r,'path',None)=='/portal/api/admin/summary' for r in app.routes)):
        raise ValueError('monthly_requires_installed_private_portal')
    origins = frozenset(x.strip() for x in os.getenv('RICHON_AUTH_ALLOWED_ORIGINS','').split(',') if x.strip())
    app.include_router(make_router(AuthSettings(origins)))

    @app.get('/portal/enrollments',include_in_schema=False)
    def page():
        return FileResponse(STATIC/'enrollments.html',headers=PAGE_HEADERS)

    @app.get('/portal/monthly-assets/{asset}',include_in_schema=False)
    def asset(asset: str):
        if asset not in {'enrollments.css','enrollments.js'}:
            raise HTTPException(404,'not_found',headers=HEADERS)
        return FileResponse(STATIC/asset,headers=HEADERS)
    return True
