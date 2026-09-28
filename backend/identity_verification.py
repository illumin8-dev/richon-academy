"""PortOne V2 identity verification adapter; raw CI is never persisted or logged."""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
import re
import secrets
import unicodedata
from urllib.parse import quote
import httpx

ID_RE = re.compile(r'richon-[A-Za-z0-9_-]{32,96}')
PUBLIC_RE = re.compile(r'[A-Za-z0-9_-]{8,160}')
BINDING_RE = re.compile(r'(richon-[A-Za-z0-9_-]{32,96})\.([a-f0-9]{64})')
TOKEN_RE = re.compile(r'[A-Za-z0-9_-]{32,160}')
MAX_RESPONSE = 65536


class VerificationRejected(Exception):
    """Fixed safe failure; never contains PortOne response bodies or personal data."""


@dataclass(frozen=True, repr=False)
class VerifiedPerson:
    ci_digest: str = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.ci_digest, str) or not re.fullmatch(r'[a-f0-9]{64}', self.ci_digest):
            raise VerificationRejected()


@dataclass(frozen=True, repr=False)
class Settings:
    store_id: str
    channel_key: str
    api_secret: str = field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.store_id, str) or not self.store_id.startswith('store-')
                or not PUBLIC_RE.fullmatch(self.store_id)):
            raise ValueError('portone_store_id_required')
        if (not isinstance(self.channel_key, str) or not self.channel_key.startswith('channel-key-')
                or not PUBLIC_RE.fullmatch(self.channel_key)):
            raise ValueError('portone_identity_channel_required')
        if (not isinstance(self.api_secret, str) or not 20 <= len(self.api_secret) <= 512
                or any(unicodedata.category(c).startswith('C') for c in self.api_secret)):
            raise ValueError('portone_api_secret_required')

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv('PORTONE_STORE_ID', ''),
            os.getenv('PORTONE_IDENTITY_CHANNEL_KEY', ''),
            os.getenv('PORTONE_API_SECRET', ''),
        )


def enabled():
    return os.getenv('RICHON_IDENTITY_VERIFICATION_ENABLED', 'false') == 'true'


def new_id():
    value = 'richon-' + secrets.token_urlsafe(24)
    if not ID_RE.fullmatch(value):
        raise VerificationRejected()
    return value


def _binding_signature(settings, browser, ticket, verification_id):
    if (not TOKEN_RE.fullmatch(browser or '') or not TOKEN_RE.fullmatch(ticket or '')
            or not ID_RE.fullmatch(verification_id or '')):
        raise VerificationRejected()
    message = ('richon/identity-binding/v1\n' + browser + '\n' + ticket + '\n' + verification_id).encode()
    return hmac.new(settings.api_secret.encode(), message, hashlib.sha256).hexdigest()


def bind(settings, browser, ticket, verification_id):
    return verification_id + '.' + _binding_signature(settings, browser, ticket, verification_id)


def require_bound(settings, browser, ticket, cookie_value, supplied_id):
    match = BINDING_RE.fullmatch(cookie_value or '')
    if not match or not ID_RE.fullmatch(supplied_id or '') or match[1] != supplied_id:
        raise VerificationRejected()
    expected = _binding_signature(settings, browser, ticket, supplied_id)
    if not hmac.compare_digest(match[2], expected):
        raise VerificationRejected()
    return supplied_id


def _client():
    return httpx.Client(timeout=httpx.Timeout(8.0), follow_redirects=False, trust_env=False)


def verify(settings, verification_id):
    if not ID_RE.fullmatch(verification_id or ''):
        raise VerificationRejected()
    url = 'https://api.portone.io/identity-verifications/' + quote(verification_id, safe='')
    try:
        with _client() as client:
            with client.stream(
                'GET', url,
                headers={'Authorization': 'PortOne ' + settings.api_secret, 'Accept': 'application/json'},
            ) as response:
                if response.status_code != 200:
                    raise VerificationRejected()
                chunks = []
                size = 0
                for block in response.iter_bytes():
                    size += len(block)
                    if size > MAX_RESPONSE:
                        raise VerificationRejected()
                    chunks.append(block)
        payload = json.loads(b''.join(chunks))
        if not isinstance(payload, dict) or payload.get('status') != 'VERIFIED':
            raise VerificationRejected()
        customer = payload.get('verifiedCustomer')
        if not isinstance(customer, dict):
            raise VerificationRejected()
        ci = customer.get('ci')
        if (not isinstance(ci, str) or not 16 <= len(ci) <= 2048 or ci != ci.strip()
                or any(unicodedata.category(c).startswith('C') for c in ci)):
            raise VerificationRejected()
        return VerifiedPerson(hashlib.sha256(ci.encode('utf-8')).hexdigest())
    except VerificationRejected:
        raise
    except Exception:
        raise VerificationRejected() from None
