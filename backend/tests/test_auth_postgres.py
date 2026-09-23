"""Auth with real SQL, ONLY in the disposable localhost CI database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import urlsplit
from uuid import uuid4
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import auth_core as core
import auth_http as http
import auth_migrate
from test_orders_postgres import postgres  # Existing create/rollback/drop fixture.

pytestmark = pytest.mark.skipif(
    os.getenv("RICHON_EMPTY_TEST_DB") != "YES" or not os.getenv("RICHON_TEST_DATABASE_URL"),
    reason="Requires the empty disposable CI PostgreSQL database",
)
CONSENT = core.SignupConsent("test-terms-v1", "test-privacy-v1")
ORIGIN = "https://richon.example.invalid"


@pytest.fixture(scope="module")
def guarded_target():
    target = urlsplit(os.environ["RICHON_TEST_DATABASE_URL"])
    if target.hostname not in {"127.0.0.1", "localhost", "::1"} or target.path != "/richon_ci":
        pytest.fail("Auth tests require the loopback richon_ci disposable database")
    if os.environ.get("DATABASE_URL"):
        pytest.fail("Refusing an application DATABASE_URL")


@pytest.fixture(scope="module")
def auth_postgres(guarded_target, request):
    # Resolve the destructive disposable fixture only AFTER checking its target.
    connect = request.getfixturevalue("postgres")
    assert auth_migrate.apply_migration()
    return connect


def identity(provider="kakao", *, subject=None, app_id="ci-app"):
    return core.VerifiedIdentity(provider, app_id, subject or uuid4().hex, "같은 가상 이름")


@pytest.fixture
def member(auth_postgres):
    return core.register_verified_identity(identity(), CONSENT)


def assert_invalid(token):
    with pytest.raises(core.AuthenticationRequired): core.resolve_session(token)


def test_auth_migration_reentry(auth_postgres):
    assert auth_migrate.apply_migration() is False
    with auth_postgres() as conn:
        assert conn.execute("SELECT count(*) FROM richon.schema_migrations WHERE version='002_auth_foundation'").fetchone() == (1,)


def test_signup_defaults_to_member_and_stable_identity(auth_postgres):
    i = identity()
    first = core.register_verified_identity(i, CONSENT)
    assert core.register_verified_identity(i, CONSENT) == first
    with auth_postgres() as conn:
        row = conn.execute("SELECT role,status,terms_version,privacy_version FROM richon.members WHERE member_id=%s", (first,)).fetchone()
    assert row == ("member", "active", "test-terms-v1", "test-privacy-v1")


def test_same_name_different_providers_never_merge(auth_postgres):
    subject = uuid4().hex
    kakao = core.register_verified_identity(identity("kakao", subject=subject), CONSENT)
    naver = core.register_verified_identity(identity("naver", subject=subject), CONSENT)
    assert kakao != naver


def test_subject_is_scoped_to_provider_application(auth_postgres):
    subject = uuid4().hex
    first = core.register_verified_identity(identity(subject=subject, app_id="test-app-a"), CONSENT)
    second = core.register_verified_identity(identity(subject=subject, app_id="test-app-b"), CONSENT)
    assert first != second


def test_concurrent_initial_login_does_not_make_duplicate_members(auth_postgres):
    i = identity()
    with auth_postgres() as conn:
        before = conn.execute("SELECT count(*) FROM richon.members").fetchone()[0]
    barrier = Barrier(4)
    def signup(_):
        barrier.wait(timeout=10)
        return core.register_verified_identity(i, CONSENT)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(signup, range(4)))
    assert len(set(results)) == 1
    with auth_postgres() as conn:
        assert conn.execute("SELECT count(*) FROM richon.members").fetchone()[0] == before + 1
    with auth_postgres() as conn:
        assert conn.execute("SELECT count(*) FROM richon.auth_identities WHERE provider=%s AND app_id=%s AND subject=%s",
                            (i.provider, i.app_id, i.subject)).fetchone() == (1,)


def test_only_digest_persisted_and_new_tokens_are_random(auth_postgres, member):
    a, b = core.issue_session(member), core.issue_session(member)
    assert a.token != b.token
    with auth_postgres() as conn:
        digests = {r[0] for r in conn.execute("SELECT token_hash FROM richon.member_sessions WHERE member_id=%s", (member,)).fetchall()}
    assert digests == {core.token_digest(a.token), core.token_digest(b.token)}
    assert a.token not in digests and b.token not in digests
    assert core.resolve_session(a.token).member_id == member
    assert_invalid("Z" * 43)


def test_session_replacement_invalidates_old_token(auth_postgres, member):
    old = core.issue_session(member)
    new = core.issue_session(member, replace_token=old.token)
    assert old.token != new.token
    assert_invalid(old.token)
    assert core.resolve_session(new.token).member_id == member


def test_single_logout_does_not_revoke_other_device(auth_postgres, member):
    a, b = core.issue_session(member), core.issue_session(member)
    core.revoke_session(a.token)
    core.revoke_session(a.token)
    assert_invalid(a.token)
    assert core.resolve_session(b.token).member_id == member


def test_all_logout_revokes_old_sessions_but_new_login_works(auth_postgres, member):
    a, b = core.issue_session(member), core.issue_session(member)
    core.revoke_all_sessions(member)
    assert_invalid(a.token)
    assert_invalid(b.token)
    new = core.issue_session(member)
    assert core.resolve_session(new.token).member_id == member


@pytest.mark.parametrize("mode", ["idle", "absolute"])
def test_server_expiration_is_enforced(auth_postgres, member, mode):
    s = core.issue_session(member)
    with auth_postgres() as conn:
        if mode == "idle":
            conn.execute("UPDATE richon.member_sessions SET idle_expires_at=CURRENT_TIMESTAMP-interval '1 second' WHERE token_hash=%s", (core.token_digest(s.token),))
        else:
            conn.execute("""UPDATE richon.member_sessions SET created_at=CURRENT_TIMESTAMP-interval '1 hour',
                expires_at=CURRENT_TIMESTAMP-interval '1 second', idle_expires_at=CURRENT_TIMESTAMP-interval '1 second'
                WHERE token_hash=%s""", (core.token_digest(s.token),))
    assert_invalid(s.token)


def test_disabled_account_cannot_resolve_login_or_issue(auth_postgres):
    i = identity()
    member = core.register_verified_identity(i, CONSENT)
    s = core.issue_session(member)
    with auth_postgres() as conn:
        conn.execute("UPDATE richon.members SET status='disabled' WHERE member_id=%s", (member,))
    assert_invalid(s.token)
    with pytest.raises(core.MemberUnavailable): core.issue_session(member)
    with pytest.raises(core.MemberUnavailable): core.register_verified_identity(i, CONSENT)


def test_role_changes_require_new_session(auth_postgres, member):
    s = core.issue_session(member)
    with auth_postgres() as conn:
        conn.execute("UPDATE richon.members SET role='admin' WHERE member_id=%s", (member,))
    assert_invalid(s.token)
    new = core.issue_session(member)
    assert core.resolve_session(new.token).role == "admin"
    with auth_postgres() as conn:
        conn.execute("UPDATE richon.members SET role='member' WHERE member_id=%s", (member,))
    assert_invalid(new.token)


def test_me_csrf_logout_against_real_database(auth_postgres, member):
    s = core.issue_session(member)
    app = FastAPI()
    app.include_router(http.make_router(http.AuthSettings(frozenset({ORIGIN}))))
    cookie = {"Cookie": f"{http.COOKIE}={s.token}"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/auth/me", headers=cookie).json()["member_id"] == str(member)
        csrf = client.get("/auth/csrf", headers=cookie).json()["csrf_token"]
        assert client.post("/auth/logout", headers={**cookie, "Origin": ORIGIN}).status_code == 403
        r = client.post("/auth/logout", headers={**cookie, "Origin": ORIGIN, "X-CSRF-Token": csrf})
        assert r.status_code == 204 and "Max-Age=0" in r.headers["set-cookie"]
        assert client.get("/auth/me", headers=cookie).status_code == 401


def test_issue_returns_no_token_when_commit_fails(auth_postgres, member):
    import psycopg
    with auth_postgres() as conn:
        conn.execute("""CREATE FUNCTION richon.auth_test_reject_commit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic auth commit failure'; END; $$""")
        conn.execute("""CREATE CONSTRAINT TRIGGER auth_test_reject_commit AFTER INSERT ON richon.member_sessions
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION richon.auth_test_reject_commit()""")
    try:
        with pytest.raises(psycopg.errors.RaiseException): core.issue_session(member)
        with auth_postgres() as conn:
            assert conn.execute("SELECT count(*) FROM richon.member_sessions WHERE member_id=%s", (member,)).fetchone() == (0,)
    finally:
        with auth_postgres() as conn:
            conn.execute("DROP TRIGGER auth_test_reject_commit ON richon.member_sessions")
            conn.execute("DROP FUNCTION richon.auth_test_reject_commit()")
