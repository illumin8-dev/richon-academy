"""Private, PG-independent pending orders. No payment or enrollment side effects."""

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, UUID4, field_validator

import db

router = APIRouter()
logger = logging.getLogger("richon.orders")
NO_STORE = {"Cache-Control": "no-store"}


class OrderRequest(BaseModel):
    # Ignore neither an injected price nor a forged payment status.
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    course_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    customer_name: str = Field(min_length=1, max_length=80, repr=False)
    customer_phone: str = Field(min_length=9, max_length=32, repr=False)
    customer_email: str = Field(min_length=3, max_length=254, repr=False)

    @field_validator("customer_name", "customer_phone", "customer_email", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        # Reject control/format characters rather than hiding them in logs or DB.
        if any(unicodedata.category(ch).startswith("C") for ch in value):
            raise ValueError("invalid_characters")
        return unicodedata.normalize("NFC", value).strip()

    @field_validator("customer_phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        value = re.sub(r"[ ()-]", "", value)
        if value.startswith("+82"):
            value = "0" + value[3:]
        if not re.fullmatch(r"(?:010[0-9]{8}|01[16789][0-9]{7,8})", value):
            raise ValueError("invalid_mobile_number")
        return value

    @field_validator("customer_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        # Syntactic validation only; this does not prove ownership/deliverability.
        parts = value.rsplit("@", 1)
        if len(parts) != 2:
            raise ValueError("invalid_email")
        local, domain = parts
        if (not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}", local)
                or local.startswith(".") or local.endswith(".") or ".." in local):
            raise ValueError("invalid_email")
        labels = domain.split(".")
        if len(labels) < 2 or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("invalid_email")
        return local + "@" + domain.lower()

    def fingerprint(self) -> str:
        canonical = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class OrderResponse(BaseModel):
    order_id: str
    course_id: str
    course_title: str
    cohort: str | None
    amount_krw: int
    currency: Literal["KRW"]
    status: Literal["pending_payment"]
    created_at: datetime


@dataclass(frozen=True)
class OrderResult:
    order: OrderResponse
    created: bool


class CourseUnavailable(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


# All identifiers are constants; every request value is a bound SQL parameter.
COLUMNS = "order_id, course_id, course_title, cohort, amount_krw, currency, status, created_at, request_fingerprint"
FIND_ORDER = f"SELECT {COLUMNS} FROM richon.orders WHERE idempotency_key = %s"
FIND_COURSE = """
    SELECT title, cohort, price_krw FROM richon.courses
    WHERE course_id = %s AND enabled = TRUE
    FOR SHARE
"""
INSERT_ORDER = f"""
    INSERT INTO richon.orders (
        order_id, idempotency_key, request_fingerprint, course_id, course_title,
        cohort, amount_krw, customer_name, customer_phone, customer_email
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING {COLUMNS}
"""


def _result(row: tuple, fingerprint: str, created: bool) -> OrderResult:
    if row[-1] != fingerprint:
        raise IdempotencyConflict()
    names = COLUMNS.split(", ")[:-1]
    return OrderResult(OrderResponse(**dict(zip(names, row[:-1], strict=True))), created)


def create_pending_order(request: OrderRequest, key: UUID4) -> OrderResult:
    """Commit one order, or return the previous order for the same attempt.

    Read committed + a unique key handles simultaneous retries in PostgreSQL.
    A separate SELECT after ON CONFLICT observes the other committed insertion.
    No background task/in-memory lock is used. Success is returned after commit.
    """
    fingerprint = request.fingerprint()
    with db._connect(db.database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute(FIND_ORDER, (str(key),))
            existing = cursor.fetchone()
            if existing is not None:
                result = _result(existing, fingerprint, created=False)
            else:
                # Lock the course while snapshotting price/title/cohort so a
                # concurrent price change/disable cannot alter this order.
                cursor.execute(FIND_COURSE, (request.course_id,))
                course = cursor.fetchone()
                if course is None:
                    raise CourseUnavailable()
                title, cohort, price = course
                cursor.execute(INSERT_ORDER, (
                    "ord_" + uuid4().hex, str(key), fingerprint,
                    request.course_id, title, cohort, price,
                    request.customer_name, request.customer_phone, request.customer_email,
                ))
                inserted = cursor.fetchone()
                if inserted is not None:
                    result = _result(inserted, fingerprint, created=True)
                else:
                    cursor.execute(FIND_ORDER, (str(key),))
                    existing = cursor.fetchone()
                    if existing is None:
                        raise RuntimeError("order_retry_required")
                    result = _result(existing, fingerprint, created=False)
    return result


@router.post("/orders", response_model=OrderResponse, status_code=201)
def post_order(
    request: OrderRequest,
    response: Response,
    idempotency_key: Annotated[UUID4, Header(alias="Idempotency-Key")],
) -> OrderResponse:
    # Cloud Run IAM protects this private API. Do not publish it as a guest API
    # until abuse limits, consent and guest-order authorization are implemented.
    response.headers.update(NO_STORE)
    try:
        result = create_pending_order(request, idempotency_key)
    except CourseUnavailable:
        raise HTTPException(404, "course_unavailable", headers=NO_STORE) from None
    except IdempotencyConflict:
        raise HTTPException(409, "idempotency_conflict", headers=NO_STORE) from None
    except Exception:
        # Never emit SQL parameters, customer details, DSN or exception text.
        logger.warning("order_storage_unavailable")
        raise HTTPException(503, "order_storage_unavailable", headers=NO_STORE) from None
    response.status_code = 201 if result.created else 200
    return result.order
