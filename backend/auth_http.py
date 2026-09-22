"""Key-free session HTTP surface. No login, fake login, signup or merge route."""
from dataclasses import dataclass
import logging
import os
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response

import auth_core as core

COOKIE = "__Host-richon-session"
NO_STORE = {"Cache-Control": "no-store"}
logger = logging.getLogger("richon.auth")


def denied(code: int, detail: str) -> HTTPException:
    return HTTPException(code, detail, headers=NO_STORE)


@dataclass(frozen=True)
class AuthSettings:
    allowed_origins: frozenset[str]

    def __post_init__(self):
        if not self.allowed_origins:
            raise ValueError("auth_origin_required")
        for origin in self.allowed_origins:
            p = urlsplit(origin)
            if (p.scheme != "https" or not p.hostname or p.username or p.password
                    or p.path or p.query or p.fragment or "*" in origin or p.netloc != p.netloc.lower()):
                raise ValueError("auth_origin_invalid")
            _ = p.port  # Validate malformed port values, without logging them.


def cookie_token(request: Request) -> str | None:
    # Reject duplicate same-name cookies rather than choosing a shadowed value.
    values = []
    for header in request.headers.getlist("cookie"):
        for pair in header.split(";"):
            name, sep, value = pair.strip().partition("=")
            if name == COOKIE and sep:
                values.append(value)
    if not values:
        return None
    if len(values) != 1:
        raise denied(401, "authentication_required")
    try:
        core.token_digest(values[0])
    except core.AuthenticationRequired:
        raise denied(401, "authentication_required") from None
    return values[0]


def require_member(request: Request) -> core.Principal:
    token = cookie_token(request)
    if token is None:
        raise denied(401, "authentication_required")
    try:
        return core.resolve_session(token)
    except core.AuthenticationRequired:
        raise denied(401, "authentication_required") from None
    except Exception:
        logger.warning("auth_store_unavailable")
        raise denied(503, "auth_store_unavailable") from None


def require_admin(member: Annotated[core.Principal, Depends(require_member)]) -> core.Principal:
    if member.role != "admin":
        raise denied(403, "admin_required")
    return member


def set_session_cookie(response: Response, session: core.IssuedSession) -> None:
    # Use only after issue_session() successfully commits. Never return the raw
    # session token in JSON, a URL, localStorage, a log, or a JavaScript cookie.
    core.token_digest(session.token)
    response.set_cookie(COOKIE, session.token, max_age=core.SESSION_SECONDS,
                        expires=session.expires_at, path="/", secure=True,
                        httponly=True, samesite="lax")
    response.headers.update(NO_STORE)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.headers.update(NO_STORE)


def _origin(request: Request, settings: AuthSettings) -> None:
    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] not in settings.allowed_origins:
        raise denied(403, "csrf_failed")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise denied(403, "csrf_failed")


def _csrf(request: Request, token: str) -> None:
    values = request.headers.getlist("x-csrf-token")
    if len(values) != 1 or not core.valid_csrf(token, values[0]):
        raise denied(403, "csrf_failed")


def make_router(settings: AuthSettings) -> APIRouter:
    router = APIRouter(prefix="/auth")

    @router.get("/me")
    def me(response: Response, member: Annotated[core.Principal, Depends(require_member)]) -> dict:
        response.headers.update(NO_STORE)
        return {"member_id": str(member.member_id), "display_name": member.display_name, "role": member.role}

    @router.get("/csrf")
    def csrf(request: Request, response: Response, member: Annotated[core.Principal, Depends(require_member)]) -> dict:
        response.headers.update(NO_STORE)
        return {"csrf_token": core.csrf_token(cookie_token(request))}

    @router.post("/logout", status_code=204)
    def logout(request: Request) -> Response:
        _origin(request, settings)
        token = cookie_token(request)
        if token is not None:
            _csrf(request, token)
            try:
                core.revoke_session(token)
            except Exception:
                logger.warning("auth_store_unavailable")
                # Do not pretend server-side revocation succeeded on DB failure.
                raise denied(503, "auth_store_unavailable") from None
        response = Response(status_code=204)
        clear_session_cookie(response)
        return response

    @router.post("/logout-all", status_code=204)
    def logout_all(request: Request, member: Annotated[core.Principal, Depends(require_member)]) -> Response:
        _origin(request, settings)
        _csrf(request, cookie_token(request))
        try:
            core.revoke_all_sessions(member.member_id)
        except Exception:
            logger.warning("auth_store_unavailable")
            raise denied(503, "auth_store_unavailable") from None
        response = Response(status_code=204)
        clear_session_cookie(response)
        return response

    return router


def install_if_enabled(app: FastAPI) -> bool:
    # No DB/auth side effect while disabled, and no accidental partial enable.
    if os.environ.get("RICHON_AUTH_ENABLED", "false") != "true":
        return False
    origins = frozenset(x.strip() for x in os.environ.get("RICHON_AUTH_ALLOWED_ORIGINS", "").split(",") if x.strip())
    app.include_router(make_router(AuthSettings(origins)))
    return True
