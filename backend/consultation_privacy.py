"""Opt-in withdrawal of optional consultation fields; not account erasure.

No DDL, provider calls, grant changes, contact updates or customer-data logging.
"""
from datetime import datetime
import logging
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

import auth_core as core
import auth_http as auth
import member_profile

FLAG = 'RICHON_CONSULTATION_WITHDRAWAL_ENABLED'
UPDATE_COLUMNS = ('age_range', 'gender', 'consultation_consent', 'consultation_withdrawn_at')
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
logger = logging.getLogger('richon.consultation_privacy')


def enabled():
    flag = os.getenv(FLAG, 'false')
    if flag not in ('true', 'false'):
        raise ValueError('invalid_consultation_withdrawal_flag')
    if flag == 'false':
        return False
    if not member_profile.enabled():
        raise ValueError('consultation_withdrawal_requires_member_policy')
    if any(os.getenv(name) != 'true' for name in ('RICHON_AUTH_ENABLED', 'RICHON_PORTAL_ENABLED')):
        raise ValueError('consultation_withdrawal_requires_portal_auth')
    return True


class EmptyQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)


class Confirmation(EmptyQuery):
    confirm: StrictBool

    @field_validator('confirm')
    @classmethod
    def affirmative(cls, value):
        if value is not True:
            raise ValueError('confirmation_required')
        return value


class WithdrawalResult(BaseModel):
    consultation_consent: Literal[False]
    age_range: None = None
    gender: None = None
    withdrawn_at: datetime | None = None


def withdraw(token):
    """Derive owner from the session, then recheck under transaction locks.

    Lock member before session, matching issue_session/logout-all. A revoked,
    expired, role-changed or disabled session must not authorize this write.
    Return only after commit; repeats preserve the first withdrawal timestamp.
    """
    if not enabled():
        raise ValueError('consultation_withdrawal_disabled')
    digest = core.token_digest(token)
    with core._transaction() as cur:
        cur.execute("""
            SELECT m.member_id FROM richon.members m
            JOIN richon.member_sessions s ON s.member_id=m.member_id
            WHERE s.token_hash=%s AND m.status='active'
            FOR SHARE OF m
        """, (digest,))
        member = cur.fetchone()
        if not member:
            raise core.AuthenticationRequired()
        cur.execute("""
            SELECT s.member_id FROM richon.member_sessions s
            JOIN richon.members m ON m.member_id=s.member_id
            WHERE s.token_hash=%s AND m.member_id=%s AND m.status='active'
              AND s.revoked_at IS NULL AND s.expires_at>CURRENT_TIMESTAMP
              AND s.idle_expires_at>CURRENT_TIMESTAMP
              AND s.auth_version=m.auth_version AND s.role_at_issue=m.role
            FOR UPDATE OF s
        """, (digest, member[0]))
        if not cur.fetchone():
            raise core.AuthenticationRequired()
        cur.execute("""
            UPDATE richon.member_profiles
            SET age_range=NULL, gender=NULL, consultation_consent=FALSE,
                consultation_withdrawn_at=CURRENT_TIMESTAMP
            WHERE member_id=%s AND consultation_consent AND over14_confirmed
              AND terms_version=%s AND privacy_version=%s
            RETURNING consultation_withdrawn_at
        """, (member[0], member_profile.VERSION, member_profile.VERSION))
        changed = cur.fetchone()
        if changed:
            stamp = changed[0]
        else:
            cur.execute("""
                SELECT consultation_withdrawn_at FROM richon.member_profiles
                WHERE member_id=%s AND NOT consultation_consent
                  AND age_range IS NULL AND gender IS NULL AND over14_confirmed
                  AND terms_version=%s AND privacy_version=%s
            """, (member[0], member_profile.VERSION, member_profile.VERSION))
            existing = cur.fetchone()
            if not existing:
                raise core.AuthenticationRequired()
            stamp = existing[0]
    return WithdrawalResult(consultation_consent=False, withdrawn_at=stamp)


def make_router(settings: auth.AuthSettings):
    router = APIRouter(prefix='/portal/api/me')

    @router.post('/consultation-consent/withdraw', response_model=WithdrawalResult)
    def withdraw_optional(request: Request, response: Response, body: Confirmation,
                          member: Annotated[core.Principal, Depends(auth.require_member)],
                          params: Annotated[EmptyQuery, Query()]):
        # No member ID, identity, role or contact value is accepted from the client.
        response.headers.update(HEADERS)
        auth._origin(request, settings)
        token = auth.cookie_token(request)
        auth._csrf(request, token)
        try:
            return withdraw(token)
        except core.AuthenticationRequired:
            raise HTTPException(401, 'authentication_required', headers=HEADERS) from None
        except Exception:
            logger.warning('consultation_withdrawal_unavailable')
            raise HTTPException(503, 'consultation_withdrawal_unavailable', headers=HEADERS) from None

    return router


def check_schema(cur):
    """Read catalog metadata only; the runtime cannot run migrations."""
    cur.execute("""
        SELECT atttypid='timestamptz'::regtype, NOT attnotnull,
               attgenerated='', attidentity=''
        FROM pg_attribute WHERE attrelid='richon.member_profiles'::regclass
          AND attname='consultation_withdrawn_at' AND NOT attisdropped
    """)
    if cur.fetchone() != (True, True, True, True):
        raise ValueError('consultation_withdrawal_schema_missing')
    cur.execute("""
        SELECT convalidated, pg_get_constraintdef(oid, false)
        FROM pg_constraint WHERE conrelid='richon.member_profiles'::regclass
          AND conname='member_profiles_consultation_withdrawn_check' AND contype='c'
    """)
    row = cur.fetchone()
    expected = 'CHECK (((consultation_withdrawn_at IS NULL) OR (NOT consultation_consent)))'
    if not row or row[0] is not True or row[1] != expected:
        raise ValueError('consultation_withdrawal_constraint_missing')
