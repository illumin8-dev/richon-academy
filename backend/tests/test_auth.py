"""Offline auth/cookie/CSRF tests. No provider tokens or real customer data."""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient
import pytest

import auth_core as core
import auth_http as http

ORIGIN = "https://richon.example.invalid"
TOKEN = "A" * 43
TOKEN2 = "B" * 43
MEMBER = core.Principal(uuid4(), "가상회원", "member", datetime.now(timezone.utc) + timedelta(hours=1))


@pytest.fixture
def client(monkeypatch):
    # Any unexpected DB call fails without accessing the network.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(core.db, "_connect", MagicMock(side_effect=AssertionError("unexpected connection")))
    monkeypatch.setattr(core, "resolve_session", MagicMock(return_value=MEMBER))
    app = FastAPI()
    app.include_router(http.make_router(http.AuthSettings(frozenset({ORIGIN}))))
    @app.get("/test-admin")
    def admin(member=Depends(http.require_admin)):
        return {"ok": True}
    with TestClient(app, base_url=ORIGIN) as c:
        yield c


def headers(token=TOKEN, *, origin=ORIGIN):
    return {"Cookie": f"{http.COOKIE}={token}", "Origin": origin,
            "X-CSRF-Token": core.csrf_token(token)}


@pytest.mark.parametrize("value", [None, "", "short", "A"*42, "A"*44, "A"*42+"!", "A"*43+"\n"])
def test_malformed_tokens_rejected(value):
    with pytest.raises(core.AuthenticationRequired): core.token_digest(value)


def test_token_hash_and_csrf_are_distinct_and_not_credentials():
    assert core.token_digest(TOKEN) != TOKEN
    assert core.csrf_token(TOKEN) != core.token_digest(TOKEN)
    assert core.csrf_token(TOKEN) != core.csrf_token(TOKEN2)
    assert core.valid_csrf(TOKEN, core.csrf_token(TOKEN))
    assert not core.valid_csrf(TOKEN2, core.csrf_token(TOKEN))
    assert not core.valid_csrf(TOKEN, "")
    assert TOKEN not in repr(core.IssuedSession(TOKEN, MEMBER.expires_at))


def test_cookie_is_host_scoped_secure_and_httponly():
    r = Response()
    http.set_session_cookie(r, core.IssuedSession(TOKEN, MEMBER.expires_at))
    value = r.headers["set-cookie"]
    for expected in ["__Host-richon-session=", "HttpOnly", "Secure", "SameSite=lax", "Path=/", "Max-Age=43200"]:
        assert expected in value
    assert "Domain=" not in value
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("origins", [frozenset(), frozenset({"*"}), frozenset({"http://example.com"}),
                                    frozenset({"https://example.com/path"}), frozenset({"https://user:pass@example.com"})])
def test_unsafe_origin_config_fails(origins):
    with pytest.raises(ValueError): http.AuthSettings(origins)


def test_disabled_flag_mounts_nothing(monkeypatch):
    monkeypatch.delenv("RICHON_AUTH_ENABLED", raising=False)
    app = FastAPI()
    assert http.install_if_enabled(app) is False
    assert TestClient(app).get("/auth/me").status_code == 404


def test_enabled_without_origin_fails_closed(monkeypatch):
    monkeypatch.setenv("RICHON_AUTH_ENABLED", "true")
    monkeypatch.delenv("RICHON_AUTH_ALLOWED_ORIGINS", raising=False)
    with pytest.raises(ValueError): http.install_if_enabled(FastAPI())


def test_missing_and_duplicate_cookies_are_rejected(client):
    assert client.get("/auth/me").status_code == 401
    both = f"{http.COOKIE}={TOKEN}; {http.COOKIE}={TOKEN2}"
    assert client.get("/auth/me", headers={"Cookie": both}).status_code == 401
    core.resolve_session.assert_not_called()


def test_me_returns_only_minimal_profile(client):
    r = client.get("/auth/me", headers=headers())
    assert r.status_code == 200
    assert set(r.json()) == {"member_id", "display_name", "role"}
    assert TOKEN not in r.text
    assert r.headers["cache-control"] == "no-store"


def test_csrf_requires_session_and_never_returns_session_token(client):
    assert client.get("/auth/csrf").status_code == 401
    r = client.get("/auth/csrf", headers=headers())
    assert r.json() == {"csrf_token": core.csrf_token(TOKEN)}
    assert TOKEN not in r.text


@pytest.mark.parametrize("change", ["missing_origin", "bad_origin", "missing_csrf", "bad_csrf", "cross_site"])
def test_logout_blocks_forged_request(client, monkeypatch, change):
    revoke = MagicMock()
    monkeypatch.setattr(core, "revoke_session", revoke)
    h = headers()
    if change == "missing_origin": del h["Origin"]
    if change == "bad_origin": h["Origin"] = ORIGIN + ".attacker.invalid"
    if change == "missing_csrf": del h["X-CSRF-Token"]
    if change == "bad_csrf": h["X-CSRF-Token"] = core.csrf_token(TOKEN2)
    if change == "cross_site": h["Sec-Fetch-Site"] = "cross-site"
    assert client.post("/auth/logout", headers=h).status_code == 403
    revoke.assert_not_called()


def test_logout_revokes_before_clearing_cookie(client, monkeypatch):
    revoke = MagicMock()
    monkeypatch.setattr(core, "revoke_session", revoke)
    r = client.post("/auth/logout", headers=headers())
    assert r.status_code == 204
    revoke.assert_called_once_with(TOKEN)
    assert "Max-Age=0" in r.headers["set-cookie"]
    assert "HttpOnly" in r.headers["set-cookie"]
    assert client.get("/auth/logout").status_code == 405


def test_logout_all_targets_current_member_only(client, monkeypatch):
    revoke = MagicMock()
    monkeypatch.setattr(core, "revoke_all_sessions", revoke)
    assert client.post("/auth/logout-all", headers=headers()).status_code == 204
    revoke.assert_called_once_with(MEMBER.member_id)


def test_logged_out_logout_is_idempotent_but_requires_origin(client):
    assert client.post("/auth/logout", headers={"Origin": ORIGIN}).status_code == 204
    assert client.post("/auth/logout").status_code == 403


def test_admin_not_trusted_from_headers(client, monkeypatch):
    h = {**headers(), "X-Role": "admin"}
    assert client.get("/test-admin", headers=h).status_code == 403
    monkeypatch.setattr(core, "resolve_session", MagicMock(return_value=core.Principal(MEMBER.member_id, "가상회원", "admin", MEMBER.expires_at)))
    assert client.get("/test-admin", headers=h).status_code == 200


@pytest.mark.parametrize("endpoint", ["/auth/me", "/auth/logout", "/auth/logout-all"])
def test_store_failure_not_success_no_secret_echo(client, monkeypatch, caplog, endpoint):
    secret = "postgresql://dummy:private-token@secret.invalid/db"
    broken = MagicMock(side_effect=RuntimeError(secret))
    for name in ["resolve_session", "revoke_session", "revoke_all_sessions"]:
        monkeypatch.setattr(core, name, broken)
    r = client.get(endpoint, headers=headers()) if endpoint.endswith("/me") else client.post(endpoint, headers=headers())
    assert r.status_code == 503
    assert secret not in r.text + caplog.text
    assert "set-cookie" not in r.headers
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/auth/login", "/auth/signup", "/auth/mock-login", "/auth/link", "/auth/merge"])
def test_no_unverified_login_or_merge_route(client, path):
    assert client.post(path, json={"member_id": str(MEMBER.member_id), "role": "admin"}).status_code == 404


def test_identity_repr_and_validation():
    identity = core.VerifiedIdentity("kakao", "app-private", "subject-private", "이름-private")
    for value in ["app-private", "subject-private", "이름-private"]: assert value not in repr(identity)
    with pytest.raises(ValueError): core.VerifiedIdentity("unknown", "a", "s", "n")
    with pytest.raises(ValueError): core.VerifiedIdentity("kakao", "a", "s\n", "n")
    with pytest.raises(ValueError): core.SignupConsent("", "privacy-v1")
