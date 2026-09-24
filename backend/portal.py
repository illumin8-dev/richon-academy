"""Read-only member/admin portal. Default OFF; no social-login bypass."""
from datetime import datetime
import logging
import os
from pathlib import Path
from typing import Annotated, Literal
import unicodedata
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth_core import Principal
from auth_http import require_member, require_admin
import portal_store as store

logger = logging.getLogger("richon.portal")
STATIC = Path(__file__).parent / "portal_static"
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
PAGE_HEADERS = {
    **HEADERS,
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
}

# Native form POST needs a same-origin Origin. APIs/admin keep no-referrer.
MEMBER_PAGE_HEADERS = {
    **PAGE_HEADERS, "Referrer-Policy": "same-origin",
    "Content-Security-Policy": PAGE_HEADERS["Content-Security-Policy"].replace(
        "style-src 'self';",
        "style-src 'self' https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css; font-src 'self' https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/;").replace("form-action 'self';", "form-action 'self' https://kauth.kakao.com https://nid.naver.com;"),
}


class EmptyQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class PageQuery(EmptyQuery):
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)


class SearchQuery(PageQuery):
    q: str = Field(default="", max_length=200)

    @field_validator("q")
    @classmethod
    def safe_text(cls, value):
        if any(unicodedata.category(ch).startswith("C") for ch in value):
            raise ValueError("invalid_search")
        return value.strip()


class MemberQuery(SearchQuery):
    status: Literal["active", "disabled"] | None = None


class CourseQuery(SearchQuery):
    enabled: bool | None = None


class OrderQuery(SearchQuery):
    linked: bool | None = None


class Profile(BaseModel):
    member_id: UUID
    display_name: str
    role: Literal["member", "admin"]
    created_at: datetime
    providers: list[Literal["kakao", "naver"]]
    linked_order_count: int


class RegistrationView(BaseModel):
    name: str
    phone: str
    email: str
    age_range: str | None
    gender: str | None
    consultation_consent: bool
    consented_at: datetime


class AccountProfile(Profile):
    registration: RegistrationView | None = None


class MemberItem(Profile):
    status: Literal["active", "disabled"]


class OrderItem(BaseModel):
    order_id: str
    course_id: str
    course_title: str
    cohort: str | None
    amount_krw: int
    currency: Literal["KRW"]
    status: Literal["pending_payment"]
    created_at: datetime


class AdminOrderItem(OrderItem):
    customer_name: str
    phone_masked: str
    email_masked: str
    member_linked: bool


class CourseItem(BaseModel):
    course_id: str
    title: str
    cohort: str | None
    price_krw: int
    enabled: bool
    created_at: datetime


class PageResult[T](BaseModel):
    items: list[T]
    limit: int
    offset: int
    has_more: bool


class Summary(BaseModel):
    members_total: int
    members_active: int
    courses_total: int
    courses_enabled: int
    orders_total: int
    pending_orders: int
    unlinked_orders: int


def read(response, operation, *args):
    response.headers.update(HEADERS)
    try:
        return operation(*args)
    except store.MissingMember:
        raise HTTPException(401, "authentication_required", headers=HEADERS) from None
    except Exception:
        logger.warning("portal_store_unavailable")
        raise HTTPException(503, "portal_store_unavailable", headers=HEADERS) from None


def make_router() -> APIRouter:
    router = APIRouter(prefix="/portal/api")

    @router.get("/me", response_model=AccountProfile, response_model_exclude_none=True)
    def me(response: Response, member: Annotated[Principal, Depends(require_member)],
           params: Annotated[EmptyQuery, Query()]):
        return read(response, store.profile, member.member_id)

    @router.get("/me/orders", response_model=PageResult[OrderItem])
    def my_orders(response: Response, member: Annotated[Principal, Depends(require_member)],
                  params: Annotated[PageQuery, Query()]):
        return read(response, store.own_orders, member.member_id, params.limit, params.offset)

    @router.get("/admin/summary", response_model=Summary)
    def admin_summary(response: Response, admin: Annotated[Principal, Depends(require_admin)],
                      params: Annotated[EmptyQuery, Query()]):
        return read(response, store.summary)

    @router.get("/admin/members", response_model=PageResult[MemberItem])
    def admin_members(response: Response, admin: Annotated[Principal, Depends(require_admin)],
                      params: Annotated[MemberQuery, Query()]):
        return read(response, store.members, params.limit, params.offset, params.q, params.status)

    @router.get("/admin/courses", response_model=PageResult[CourseItem])
    def admin_courses(response: Response, admin: Annotated[Principal, Depends(require_admin)],
                      params: Annotated[CourseQuery, Query()]):
        return read(response, store.courses, params.limit, params.offset, params.q, params.enabled)

    @router.get("/admin/orders", response_model=PageResult[AdminOrderItem])
    def admin_orders(response: Response, admin: Annotated[Principal, Depends(require_admin)],
                     params: Annotated[OrderQuery, Query()]):
        return read(response, store.orders, params.limit, params.offset, params.q, params.linked)

    return router


def install_if_enabled(app: FastAPI) -> bool:
    if os.environ.get("RICHON_PORTAL_ENABLED", "false") != "true":
        return False
    if os.environ.get("RICHON_AUTH_ENABLED") != "true":
        raise ValueError("portal_requires_auth")
    # install auth first so its origin configuration also fails closed.
    if not any(getattr(r, "path", None) == "/auth/me" for r in app.routes):
        raise ValueError("portal_auth_not_installed")
    app.include_router(make_router())

    @app.middleware("http")
    async def private_portal_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/portal/"):
            response.headers.update(MEMBER_PAGE_HEADERS if request.url.path == "/portal/mypage" and response.status_code == 200 else PAGE_HEADERS)
        return response

    # Pages contain only the UI shell. Protected APIs decide every data access.
    @app.get("/portal/mypage", include_in_schema=False)
    def mypage():
        return FileResponse(STATIC / "mypage.html", headers=MEMBER_PAGE_HEADERS)

    @app.get("/portal/admin", include_in_schema=False)
    def admin_page():
        return FileResponse(STATIC / "admin.html", headers=PAGE_HEADERS)

    @app.get("/portal/assets/{asset}", include_in_schema=False)
    def asset(asset: str):
        if asset not in {"portal.css", "portal.js", "site.css", "site.js", "login.js", "account.css", "account.js"}:
            raise HTTPException(404, "not_found", headers=HEADERS)
        return FileResponse(STATIC / asset, headers=HEADERS)
    return True
