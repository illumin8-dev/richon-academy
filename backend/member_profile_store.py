"""Atomic opt-in registration. No identity inference from names or contacts."""
import hashlib
import json
import re
from uuid import uuid4
import auth_core as core
import member_profile as profile
import marketing_consent as marketing
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
            RETURNING provider,app_id,subject,display_name,
                      provider_name,provider_phone,provider_email,
                      provider_age_range,provider_gender,provider_ci_digest,return_to''',
            (digest, browser_digest, settings.terms_version, settings.privacy_version))
        row = cur.fetchone()
        if (not row or row[0] not in settings.providers
                or settings.providers[row[0]].identity_scope != row[1] or row[10] not in RETURNS):
            raise InvalidFlow()
        identity = core.VerifiedIdentity(*row[:4])
        ci_digest = row[9]
        if identity.provider == 'kakao' and (
                not isinstance(ci_digest, str) or not re.fullmatch(r'[a-f0-9]{64}', ci_digest)):
            raise InvalidFlow()
        if identity.provider != 'kakao' and ci_digest is not None:
            raise InvalidFlow()
        age_range = (row[7] or registration.age_range) if registration.consultation_consent else None
        gender = (row[8] or registration.gender) if registration.consultation_consent else None
        effective = profile.Registration(
            row[4] or registration.name,
            row[5] or registration.phone,
            row[6] or registration.email,
            age_range, gender,
            registration.consultation_consent, True)
        scope = json.dumps([identity.provider, identity.app_id, identity.subject], separators=(',', ':'))
        lock = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], 'big', signed=True)
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
        if ci_digest is not None:
            ci_lock = int.from_bytes(hashlib.sha256(('richon/ci/v1/'+ci_digest).encode()).digest()[:8],
                                     'big', signed=True)
            cur.execute('SELECT pg_advisory_xact_lock(%s)', (ci_lock,))
        cur.execute('''SELECT m.member_id,m.status FROM richon.auth_identities i
            JOIN richon.members m USING(member_id)
            WHERE i.provider=%s AND i.app_id=%s AND i.subject=%s FOR SHARE OF m''',
            (identity.provider, identity.app_id, identity.subject))
        member = cur.fetchone()
        if member and member[1] != 'active':
            raise core.MemberUnavailable()
        member_id = member[0] if member else uuid4()
        if ci_digest is not None:
            cur.execute('''SELECT c.member_id,m.status
                           FROM richon.member_ci_claims c JOIN richon.members m USING(member_id)
                           WHERE c.ci_digest=%s FOR SHARE OF m''',(ci_digest,))
            claim=cur.fetchone()
            if claim and (claim[1] != 'active' or claim[0] != member_id):
                raise InvalidFlow()
        if not member:
            cur.execute('''INSERT INTO richon.members(member_id,display_name,terms_version,privacy_version)
                VALUES(%s,%s,%s,%s)''',
                (member_id, effective.name, settings.terms_version, settings.privacy_version))
            cur.execute('''INSERT INTO richon.auth_identities(provider,app_id,subject,member_id)
                VALUES(%s,%s,%s,%s)''', (identity.provider, identity.app_id, identity.subject, member_id))
        if ci_digest is not None:
            cur.execute('''INSERT INTO richon.member_ci_claims(ci_digest,member_id,provider)
                           VALUES(%s,%s,'kakao') ON CONFLICT (ci_digest) DO NOTHING''',
                        (ci_digest,member_id))
            if cur.rowcount == 0:
                cur.execute('SELECT member_id FROM richon.member_ci_claims WHERE ci_digest=%s',(ci_digest,))
                if cur.fetchone() != (member_id,):
                    raise InvalidFlow()
        cur.execute('SELECT terms_version,privacy_version FROM richon.member_profiles WHERE member_id=%s', (member_id,))
        existing = cur.fetchone()
        if existing and existing != (settings.terms_version, settings.privacy_version):
            raise InvalidFlow()
        if not existing:
            cur.execute('''INSERT INTO richon.member_profiles
                (member_id,name,phone,email,age_range,gender,consultation_consent,
                 over14_confirmed,terms_version,privacy_version)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (member_id, effective.name, effective.phone, effective.email,
                 effective.age_range, effective.gender, effective.consultation_consent,
                 True, settings.terms_version, settings.privacy_version))
        if marketing.enabled():
            granted=registration.marketing_consent
            cur.execute('''INSERT INTO richon.member_marketing_consents
                (member_id,email_enabled,sms_enabled,consent_version,last_consented_at)
                VALUES(%s,%s,%s,%s,CASE WHEN %s THEN CURRENT_TIMESTAMP END)
                ON CONFLICT (member_id) DO NOTHING''',
                (member_id,granted,granted,marketing.VERSION,granted))
    return member_id, row[10]
