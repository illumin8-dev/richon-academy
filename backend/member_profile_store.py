"""Atomic opt-in registration. No identity inference from names or contacts."""
import hashlib
import json
from uuid import uuid4
import auth_core as core
import member_profile as profile
from oauth_providers import RETURNS
from oauth_store import InvalidFlow


def completed(member_id, settings):
    if not profile.enabled(settings.terms_version, settings.privacy_version):
        return True
    with core._transaction() as cur:
        cur.execute('''SELECT 1 FROM richon.member_profiles WHERE member_id=%s
            AND terms_version=%s AND privacy_version=%s AND over14_confirmed''',
            (member_id, settings.terms_version, settings.privacy_version))
        return cur.fetchone() == (1,)


def finish(settings, ticket, browser, registration):
    """One commit for ticket consumption, identity, profile and consent evidence.

    Existing identities retain member_id and role. Concurrent first submissions
    use the same identity lock as auth_core. A later ticket cannot edit an already
    completed profile, even if the submitted name/contact fields differ.
    """
    if not profile.enabled(settings.terms_version, settings.privacy_version):
        raise InvalidFlow()
    if not isinstance(registration, profile.Registration):
        raise InvalidFlow()
    digest, browser_digest = core.token_digest(ticket), core.token_digest(browser)
    with core._transaction() as cur:
        # DELETE RETURNING uses the existing DELETE grant, unlike SELECT FOR
        # UPDATE which would also require an unapproved ticket UPDATE grant.
        # A later failure rolls this deletion back in the same transaction.
        cur.execute('''DELETE FROM richon.oauth_signups WHERE ticket_hash=%s AND browser_hash=%s
            AND expires_at>CURRENT_TIMESTAMP AND terms_version=%s AND privacy_version=%s
            RETURNING provider,app_id,subject,display_name,return_to''', (digest, browser_digest, settings.terms_version, settings.privacy_version))
        row = cur.fetchone()
        if (not row or row[0] not in settings.providers
                or settings.providers[row[0]].identity_scope != row[1] or row[4] not in RETURNS):
            raise InvalidFlow()
        identity = core.VerifiedIdentity(*row[:4])
        scope = json.dumps([identity.provider, identity.app_id, identity.subject], separators=(',', ':'))
        lock = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], 'big', signed=True)
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
        cur.execute('''SELECT m.member_id,m.status FROM richon.auth_identities i
            JOIN richon.members m USING(member_id)
            WHERE i.provider=%s AND i.app_id=%s AND i.subject=%s FOR SHARE OF m''',
            (identity.provider, identity.app_id, identity.subject))
        member = cur.fetchone()
        if member and member[1] != 'active':
            raise core.MemberUnavailable()
        member_id = member[0] if member else uuid4()
        if not member:
            cur.execute('''INSERT INTO richon.members(member_id,display_name,terms_version,privacy_version)
                VALUES(%s,%s,%s,%s)''',
                (member_id, registration.name, settings.terms_version, settings.privacy_version))
            cur.execute('''INSERT INTO richon.auth_identities(provider,app_id,subject,member_id)
                VALUES(%s,%s,%s,%s)''', (identity.provider, identity.app_id, identity.subject, member_id))
        cur.execute('SELECT terms_version,privacy_version FROM richon.member_profiles WHERE member_id=%s', (member_id,))
        existing = cur.fetchone()
        if existing and existing != (settings.terms_version, settings.privacy_version):
            raise InvalidFlow()
        if not existing:
            cur.execute('''INSERT INTO richon.member_profiles
                (member_id,name,phone,email,age_range,gender,consultation_consent,
                 over14_confirmed,terms_version,privacy_version)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (member_id, registration.name, registration.phone, registration.email,
                 registration.age_range, registration.gender, registration.consultation_consent,
                 True, settings.terms_version, settings.privacy_version))
    return member_id, row[4]
