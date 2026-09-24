"""Approved member-info-v1 rules. Pure validation; no automatic collection."""
from dataclasses import dataclass, field
import os
import re
import unicodedata

VERSION = 'member-info-v1'
AGE_RANGES = ('14-19', '20-29', '30-39', '40-49', '50-59', '60-69', '70+')
GENDERS = ('female', 'male')
INSERT_COLUMNS = ('member_id', 'name', 'phone', 'email', 'age_range', 'gender',
                  'consultation_consent', 'over14_confirmed', 'terms_version', 'privacy_version')


class InvalidProfile(ValueError):
    """Fixed safe code only. Never include submitted personal information."""


def enabled(terms=None, privacy=None):
    terms = os.getenv('RICHON_TERMS_VERSION', '') if terms is None else terms
    privacy = os.getenv('RICHON_PRIVACY_VERSION', '') if privacy is None else privacy
    if VERSION in (terms, privacy) and terms != privacy:
        raise ValueError('member_policy_version_mismatch')
    return terms == privacy == VERSION


def clean_name(value):
    if (not isinstance(value, str) or len(value) > 80
            or any(unicodedata.category(c).startswith('C') for c in value)):
        raise InvalidProfile('invalid_name')
    value = unicodedata.normalize('NFC', value).strip()
    if not value or not any(unicodedata.category(c).startswith('L') for c in value):
        raise InvalidProfile('invalid_name')
    if any(not (unicodedata.category(c)[0] in 'LM' or c in " .'-·") for c in value):
        raise InvalidProfile('invalid_name')
    return value


def clean_phone(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+0-9 ()-]{8,32}', value):
        raise InvalidProfile('invalid_phone')
    value = re.sub(r'[ ()-]', '', value)
    if value.startswith('+82'):
        value = '0' + value[3:]
    if not (re.fullmatch(r'01[016789][0-9]{7,8}', value)
            or re.fullmatch(r'\+[1-9][0-9]{7,14}', value)):
        raise InvalidProfile('invalid_phone')
    return value


def clean_email(value):
    if (not isinstance(value, str) or len(value) > 254 or not value.isascii()
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise InvalidProfile('invalid_email')
    value = value.strip()
    if value.count('@') != 1:
        raise InvalidProfile('invalid_email')
    local, domain = value.rsplit('@', 1)
    if (not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local)
            or local.startswith('.') or local.endswith('.') or '..' in local
            or '.' not in domain or len(domain) > 253
            or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p)
                   for p in domain.split('.'))):
        raise InvalidProfile('invalid_email')
    return local + '@' + domain.lower()


@dataclass(frozen=True, repr=False)
class Registration:
    name: str = field(repr=False)
    phone: str = field(repr=False)
    email: str = field(repr=False)
    age_range: str | None = field(default=None, repr=False)
    gender: str | None = field(default=None, repr=False)
    consultation_consent: bool = False
    over14_confirmed: bool = True

    def __post_init__(self):
        if self.over14_confirmed is not True or type(self.consultation_consent) is not bool:
            raise InvalidProfile('consent_required')
        object.__setattr__(self, 'name', clean_name(self.name))
        object.__setattr__(self, 'phone', clean_phone(self.phone))
        object.__setattr__(self, 'email', clean_email(self.email))
        # Ignore even malicious optional values when permission was not given.
        if not self.consultation_consent:
            object.__setattr__(self, 'age_range', None)
            object.__setattr__(self, 'gender', None)
        elif self.age_range not in (None, *AGE_RANGES) or self.gender not in (None, *GENDERS):
            raise InvalidProfile('invalid_consultation_fields')

    @classmethod
    def from_form(cls, data):
        if (data.get('terms') != 'yes' or data.get('privacy') != 'yes'
                or data.get('over14') != 'yes' or data.get('terms_version') != VERSION
                or data.get('privacy_version') != VERSION
                or data.get('consultation', '') not in ('', 'yes')):
            raise InvalidProfile('consent_required')
        return cls(data.get('name'), data.get('phone'), data.get('email'),
                   data.get('age_range') or None, data.get('gender') or None,
                   data.get('consultation') == 'yes', True)
