"""Provider-independent member/session groundwork, not an OAuth verifier.

Identity input MUST come from a future server-side provider adapter after token,
state and callback validation, never directly from an HTTP request. No public
login or account-linking endpoint is provided by this module.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from uuid import UUID, uuid4

import db

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
SESSION_SECONDS = 12 * 60 * 60  # Development defaults; confirm UX before launch.
IDLE_SECONDS = 30 * 60


class AuthenticationRequired(Exception):
    """No valid active session; never include input values."""


class MemberUnavailable(Exception):
    """Existing identity belongs to an inactive member."""


def _text(value: str, limit: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise ValueError("invalid_identity_input")
    if value != value.strip() or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("invalid_identity_input")
    return value


@dataclass(frozen=True)
class VerifiedIdentity:
    """Internal adapter output type. Constructing it does NOT verify identity."""
    provider: str
    app_id: str = field(repr=False)
    subject: str = field(repr=False)
    display_name: str = field(repr=False)

    def __post_init__(self):
        if self.provider not in {"kakao", "naver"}:
            raise ValueError("unsupported_provider")
        _text(self.app_id, 200)
        _text(self.subject, 255)
        _text(self.display_name, 80)


@dataclass(frozen=True)
class SignupConsent:
    """Pass only after the service's own required consent UI is accepted."""
    terms_version: str
    privacy_version: str

    def __post_init__(self):
        for value in (self.terms_version, self.privacy_version):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value):
                raise ValueError("invalid_consent_version")


@dataclass(frozen=True)
class Principal:
    member_id: UUID
    display_name: str = field(repr=False)
    role: str
    expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    token: str = field(repr=False)
    expires_at: datetime


def token_digest(token: str) -> str:
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise AuthenticationRequired()
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_token(token: str) -> str:
    """Session-bound CSRF proof; cannot be used as a session credential."""
    token_digest(token)
    return hmac.new(token.encode("ascii"), b"richon/csrf/v1", hashlib.sha256).hexdigest()


def valid_csrf(token: str, supplied: str | None) -> bool:
    if not isinstance(supplied, str) or not re.fullmatch(r"[a-f0-9]{64}", supplied):
        return False
    return hmac.compare_digest(csrf_token(token), supplied)


@contextmanager
def _transaction():
    # Reuse the existing verified TLS connection. No session data in globals.
    with db._connect(db.database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            yield cursor
    # Successful return to callers occurs only after commit.


def register_verified_identity(identity: VerifiedIdentity, consent: SignupConsent) -> UUID:
    """One provider/app/subject -> one member. Never match names/phones/emails.

    Existing identities are not moved; profile values do not overwrite member
    data on a later login. Account linking requires a separate approved flow.
    """
    scope = json.dumps([identity.provider, identity.app_id, identity.subject], separators=(",", ":"))
    lock = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], "big", signed=True)
    with _transaction() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
        cur.execute("""
            SELECT m.member_id, m.status FROM richon.auth_identities i
            JOIN richon.members m ON m.member_id=i.member_id
            WHERE i.provider=%s AND i.app_id=%s AND i.subject=%s
        """, (identity.provider, identity.app_id, identity.subject))
        existing = cur.fetchone()
        if existing:
            if existing[1] != "active":
                raise MemberUnavailable()
            member_id = existing[0]
        else:
            member_id = uuid4()
            cur.execute("""
                INSERT INTO richon.members
                    (member_id, display_name, terms_version, privacy_version)
                VALUES (%s, %s, %s, %s)
            """, (member_id, identity.display_name, consent.terms_version, consent.privacy_version))
            cur.execute("""
                INSERT INTO richon.auth_identities (provider, app_id, subject, member_id)
                VALUES (%s, %s, %s, %s)
            """, (identity.provider, identity.app_id, identity.subject, member_id))
    return member_id


def issue_session(member_id: UUID, *, replace_token: str | None = None) -> IssuedSession:
    """Internal only: call after fresh provider authentication and consent.

    Always generate a new secret. An old same-member session can be atomically
    revoked when replacing it. Never issue credentials from a supplied member ID
    in a public handler or based on matching name/contact fields.
    """
    if not isinstance(member_id, UUID):
        raise ValueError("invalid_member_id")
    token = secrets.token_urlsafe(32)
    digest = token_digest(token)
    old_digest = token_digest(replace_token) if replace_token is not None else None
    with _transaction() as cur:
        # Serialize session creation against logout-all's member-version update.
        cur.execute("SELECT role, auth_version, status FROM richon.members WHERE member_id=%s FOR SHARE", (member_id,))
        row = cur.fetchone()
        if not row or row[2] != "active":
            raise MemberUnavailable()
        role, version, _ = row
        if old_digest:
            cur.execute("""UPDATE richon.member_sessions SET revoked_at=CURRENT_TIMESTAMP
                           WHERE token_hash=%s AND member_id=%s AND revoked_at IS NULL""", (old_digest, member_id))
        cur.execute("""
            INSERT INTO richon.member_sessions
                (token_hash, member_id, auth_version, role_at_issue, expires_at, idle_expires_at)
            VALUES (%s,%s,%s,%s,CURRENT_TIMESTAMP + %s * interval '1 second',
                   CURRENT_TIMESTAMP + %s * interval '1 second') RETURNING expires_at
        """, (digest, member_id, version, role, SESSION_SECONDS, IDLE_SECONDS))
        expires_at = cur.fetchone()[0]
    return IssuedSession(token, expires_at)


def resolve_session(token: str) -> Principal:
    """Read current role/status/version, not a role trusted from a cookie."""
    digest = token_digest(token)
    with _transaction() as cur:
        cur.execute("""
            SELECT m.member_id, m.display_name, m.role, s.expires_at
            FROM richon.member_sessions s JOIN richon.members m ON m.member_id=s.member_id
            WHERE s.token_hash=%s AND s.revoked_at IS NULL
              AND s.expires_at>CURRENT_TIMESTAMP AND s.idle_expires_at>CURRENT_TIMESTAMP
              AND m.status='active' AND s.auth_version=m.auth_version AND s.role_at_issue=m.role
            FOR UPDATE OF s
        """, (digest,))
        row = cur.fetchone()
        if not row:
            raise AuthenticationRequired()
        cur.execute("""
            UPDATE richon.member_sessions SET last_seen_at=CURRENT_TIMESTAMP,
                   idle_expires_at=LEAST(expires_at, CURRENT_TIMESTAMP + %s * interval '1 second')
            WHERE token_hash=%s
        """, (IDLE_SECONDS, digest))
        principal = Principal(*row)
    return principal


def revoke_session(token: str) -> None:
    digest = token_digest(token)
    with _transaction() as cur:
        cur.execute("""UPDATE richon.member_sessions SET revoked_at=CURRENT_TIMESTAMP
                       WHERE token_hash=%s AND revoked_at IS NULL""", (digest,))


def revoke_all_sessions(member_id: UUID) -> None:
    """Invalidate existing sessions with a version bump, atomically."""
    with _transaction() as cur:
        cur.execute("UPDATE richon.members SET auth_version=auth_version+1 WHERE member_id=%s", (member_id,))
        cur.execute("""UPDATE richon.member_sessions SET revoked_at=CURRENT_TIMESTAMP
                       WHERE member_id=%s AND revoked_at IS NULL""", (member_id,))
