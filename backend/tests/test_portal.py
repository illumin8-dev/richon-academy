"""Portal contract tests: no real database, no external providers."""
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import auth_http
from auth_core import Principal
from main import invalid_request
from fastapi.exceptions import RequestValidationError
import portal
import portal_store

ORIGIN = "https://richon.example.invalid"


def app_with_portal(monkeypatch):
    monkeypatch.setenv("RICHON_AUTH_ENABLED", "true")
    monkeypatch.setenv("RICHON_PORTAL_ENABLED", "true")
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.include_router(auth_http.make_router(auth_http.AuthSettings(frozenset({ORIGIN}))))
    assert portal.install_if_enabled(app)
    return app


@pytest.fixture
def app(monkeypatch):
    return app_with_portal(monkeypatch)


@pytest.mark.parametrize("path", ["/portal/mypage", "/portal/admin", "/portal/api/me", "/portal/assets/portal.js"])
def test_default_off(monkeypatch, path):
    monkeypatch.delenv("RICHON_PORTAL_ENABLED", raising=False)
    app = FastAPI()
    assert portal.install_if_enabled(app) is False
    assert TestClient(app).get(path).status_code == 404


def test_cannot_enable_without_auth(monkeypatch):
    monkeypatch.setenv("RICHON_PORTAL_ENABLED", "true")
    monkeypatch.setenv("RICHON_AUTH_ENABLED", "false")
    with pytest.raises(ValueError): portal.install_if_enabled(FastAPI())
    monkeypatch.setenv("RICHON_AUTH_ENABLED", "true")
    with pytest.raises(ValueError): portal.install_if_enabled(FastAPI())


@pytest.mark.parametrize("path", ["me", "me/orders", "admin/summary", "admin/members", "admin/courses", "admin/orders"])
def test_unauthenticated_never_queries_domain_store(app, monkeypatch, path):
    read = Mock(side_effect=AssertionError("unauthenticated domain query"))
    monkeypatch.setattr(portal, "read", read)
    response = TestClient(app).get("/portal/api/" + path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    read.assert_not_called()


@pytest.mark.parametrize("path", ["summary", "members", "courses", "orders"])
def test_member_cannot_access_admin(app, monkeypatch, path):
    principal = Principal(uuid4(), "가상 회원", "member", datetime.now(timezone.utc))
    app.dependency_overrides[auth_http.require_member] = lambda: principal
    read = Mock(side_effect=AssertionError("non-admin domain query"))
    monkeypatch.setattr(portal, "read", read)
    assert TestClient(app).get("/portal/api/admin/" + path).status_code == 403
    read.assert_not_called()


@pytest.mark.parametrize("query", ["member_id=other", "limit=0", "limit=51", "offset=-1", "offset=10001", "role=admin"])
def test_owned_orders_reject_invalid_or_injected_query(app, monkeypatch, query):
    app.dependency_overrides[auth_http.require_member] = lambda: Principal(uuid4(), "가상", "member", datetime.now(timezone.utc))
    query_db = Mock()
    monkeypatch.setattr(portal_store, "own_orders", query_db)
    response = TestClient(app).get("/portal/api/me/orders?" + query)
    assert response.status_code == 422 and response.json() == {"detail": "invalid_request"}
    query_db.assert_not_called()


def test_own_id_comes_only_from_session(app, monkeypatch):
    owner = uuid4()
    app.dependency_overrides[auth_http.require_member] = lambda: Principal(owner, "가상", "member", datetime.now(timezone.utc))
    query = Mock(return_value={"items":[],"limit":20,"offset":0,"has_more":False})
    monkeypatch.setattr(portal_store, "own_orders", query)
    response = TestClient(app).get("/portal/api/me/orders")
    assert response.status_code == 200
    query.assert_called_once_with(owner, 20, 0)


def test_database_failure_not_false_empty_list(app, monkeypatch, caplog):
    app.dependency_overrides[auth_http.require_member] = lambda: Principal(uuid4(), "가상", "member", datetime.now(timezone.utc))
    monkeypatch.setattr(portal_store, "own_orders", Mock(side_effect=RuntimeError("secret-dsn-and-personal-data-marker")))
    response = TestClient(app).get("/portal/api/me/orders")
    assert response.status_code == 503
    assert response.json() == {"detail":"portal_store_unavailable"}
    assert "secret-dsn-and-personal-data-marker" not in response.text + caplog.text


@pytest.mark.parametrize("page", ["mypage", "admin"])
def test_ui_shell_has_no_customer_data_and_restricts_resources(app, page):
    response = TestClient(app).get("/portal/" + page)
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == ("same-origin" if page == "mypage" else "no-referrer")
    assert "noindex,nofollow" in response.text
    assert ('<script defer src="/portal/assets/account.js">' if page == 'mypage' else '<script defer src="/portal/assets/portal.js">') in response.text
    assert 'id="content" hidden' in response.text
    assert "01000000000" not in response.text


@pytest.mark.parametrize("file", ["AUTH.md", "portal.py", ".env", "003_portal_read_models.sql"])
def test_arbitrary_files_not_served(app, file):
    assert TestClient(app).get("/portal/assets/" + file).status_code == 404


def test_sql_search_escapes_wildcards():
    assert portal_store._literal_search("a%_\\b") == "%a\\%\\_\\\\b%"


def test_assets_use_text_nodes_and_no_token_storage():
    js = (portal.STATIC / "portal.js").read_text()
    for forbidden in ("innerHTML", "insertAdjacentHTML", "localStorage.", "sessionStorage.", "document.cookie", "eval("):
        assert forbidden not in js
    assert "textContent" in js and "credentials:'same-origin'" in js
