"""Own-account profile, provider linking, unlink and withdrawal transactions.

Every member_id comes from an authenticated server-side Principal. Names,
telephone numbers and email addresses are never used to infer identity.
Provider access tokens are never stored in this module.
"""
from dataclasses import dataclass
import hashlib
import json
import secrets
from uuid import UUID, uuid4

import auth_core as core
import member_profile as profile

FRESH_SECONDS = 10 * 60
ACTIONS = frozenset({'link','reauth','unlink','withdraw'})


class AccountActionRejected(Exception): pass
class AlreadyLinked(AccountActionRejected): pass
class ProviderNotLinked(AccountActionRejected): pass
class IdentityInUse(AccountActionRejected): pass
class LastLoginMethod(AccountActionRejected): pass
class ProfileUnavailable(AccountActionRejected): pass
class AdminWithdrawalNotAllowed(AccountActionRejected): pass
class LifecycleNotReady(AccountActionRejected): pass
class WithdrawalNotPrepared(AccountActionRejected): pass
class WithdrawalInProgress(AccountActionRejected): pass


@dataclass(frozen=True)
class AccountAttempt:
    member_id: UUID
    action: str
    provider: str
    app_id: str


def _scope(settings, provider):
    if provider not in settings.providers:
        raise AccountActionRejected()
    return settings.providers[provider].identity_scope


def _identity_lock(provider, app_id, subject):
    value=json.dumps([provider,app_id,subject],separators=(',',':'))
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8],'big',signed=True)


def _providers_cur(cur, member_id, settings):
    scopes={name:cfg.identity_scope for name,cfg in settings.providers.items()}
    cur.execute('SELECT provider,app_id FROM richon.auth_identities WHERE member_id=%s ORDER BY provider',(member_id,))
    return [provider for provider,app_id in cur.fetchall()
            if provider in scopes and scopes[provider]==app_id]


def providers_for(member_id, settings):
    with core._transaction() as cur:
        return _providers_cur(cur,member_id,settings)


def update_profile(member_id, registration):
    if not isinstance(registration,profile.Registration):
        raise ProfileUnavailable()
    with core._transaction() as cur:
        cur.execute('SELECT status FROM richon.members WHERE member_id=%s FOR UPDATE',(member_id,))
        row=cur.fetchone()
        if not row or row[0]!='active':
            raise core.MemberUnavailable()
        cur.execute('SELECT 1 FROM richon.member_profiles WHERE member_id=%s',(member_id,))
        if cur.fetchone()!=(1,):
            raise ProfileUnavailable()
        cur.execute('''UPDATE richon.member_profiles
            SET name=%s,phone=%s,email=%s,age_range=%s,gender=%s,consultation_consent=%s
            WHERE member_id=%s''',
            (registration.name,registration.phone,registration.email,registration.age_range,
             registration.gender,registration.consultation_consent,member_id))
        cur.execute('UPDATE richon.members SET display_name=%s WHERE member_id=%s',
                    (registration.name,member_id))


def recent_session(token, member_id, seconds=FRESH_SECONDS):
    digest=core.token_digest(token)
    if not isinstance(member_id,UUID) or not isinstance(seconds,int) or not 60<=seconds<=3600:
        return False
    with core._transaction() as cur:
        cur.execute('''SELECT 1 FROM richon.member_sessions s JOIN richon.members m USING(member_id)
            WHERE s.token_hash=%s AND s.member_id=%s AND s.revoked_at IS NULL
              AND s.expires_at>CURRENT_TIMESTAMP AND s.idle_expires_at>CURRENT_TIMESTAMP
              AND s.auth_version=m.auth_version AND s.role_at_issue=m.role
              AND m.status='active'
              AND s.created_at>=CURRENT_TIMESTAMP-%s*interval '1 second' ''',
            (digest,member_id,seconds))
        return cur.fetchone()==(1,)


def withdrawal_ready(cur, member_id):
    cur.execute('SELECT role,status FROM richon.members WHERE member_id=%s FOR UPDATE',(member_id,))
    row=cur.fetchone()
    if not row or row[1]!='active':
        raise core.MemberUnavailable()
    if row[0]=='admin':
        raise AdminWithdrawalNotAllowed()
    # Course/enrollment history is not an authentication dependency. If the
    # optional enrollment schema exists, finalize_withdrawal() detaches the
    # member and scrubs its contact fields while preserving course history.
    cur.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id=%s',(member_id,))
    if cur.fetchone()[0] < 1:
        raise LifecycleNotReady()


def prepare_withdrawal(member_id):
    with core._transaction() as cur:
        withdrawal_ready(cur,member_id)
        cur.execute('DELETE FROM richon.oauth_link_confirmations WHERE member_id=%s',(member_id,))
        cur.execute('DELETE FROM richon.oauth_account_attempts WHERE member_id=%s',(member_id,))
        cur.execute('DELETE FROM richon.account_withdrawals WHERE member_id=%s',(member_id,))
        cur.execute('''INSERT INTO richon.account_withdrawals(member_id,expires_at)
                       VALUES(%s,CURRENT_TIMESTAMP+interval '30 minutes')''',(member_id,))


def cancel_withdrawal(member_id):
    with core._transaction() as cur:
        cur.execute('DELETE FROM richon.account_withdrawals WHERE member_id=%s',(member_id,))


def withdrawal_status(member_id, settings):
    with core._transaction() as cur:
        cur.execute('''SELECT 1 FROM richon.account_withdrawals
                       WHERE member_id=%s AND expires_at>CURRENT_TIMESTAMP''',(member_id,))
        if cur.fetchone()!=(1,):
            return None
        return _providers_cur(cur,member_id,settings)


def begin_action(settings, member_id, provider, action, browser):
    if action not in ACTIONS:
        raise AccountActionRejected()
    app_id=_scope(settings,provider)
    state=secrets.token_urlsafe(32)
    browser_hash=core.token_digest(browser)
    with core._transaction() as cur:
        cur.execute('SELECT status FROM richon.members WHERE member_id=%s FOR SHARE',(member_id,))
        row=cur.fetchone()
        if not row or row[0]!='active':
            raise core.MemberUnavailable()
        cur.execute('''SELECT 1 FROM richon.account_withdrawals
                       WHERE member_id=%s AND expires_at>CURRENT_TIMESTAMP''',(member_id,))
        withdrawing=cur.fetchone()==(1,)
        if action in ('link','unlink') and withdrawing:
            raise WithdrawalInProgress()
        cur.execute('''SELECT 1 FROM richon.auth_identities
                       WHERE member_id=%s AND provider=%s AND app_id=%s''',
                    (member_id,provider,app_id))
        linked=cur.fetchone()==(1,)
        if action=='link' and linked:
            raise AlreadyLinked()
        if action in ('reauth','unlink','withdraw') and not linked:
            raise ProviderNotLinked()
        if action=='unlink':
            cur.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id=%s',(member_id,))
            if cur.fetchone()[0] <= 1:
                raise LastLoginMethod()
        if action=='withdraw':
            cur.execute('''SELECT 1 FROM richon.account_withdrawals
                           WHERE member_id=%s AND expires_at>CURRENT_TIMESTAMP''',(member_id,))
            if cur.fetchone()!=(1,):
                raise WithdrawalNotPrepared()
        cur.execute('''DELETE FROM richon.oauth_account_attempts
                       WHERE expires_at<CURRENT_TIMESTAMP OR
                             (member_id=%s AND provider=%s AND action=%s)''',
                    (member_id,provider,action))
        cur.execute('''INSERT INTO richon.oauth_account_attempts
            (state_hash,browser_hash,member_id,provider,app_id,action,expires_at)
            VALUES(%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP+interval '5 minutes')''',
            (core.token_digest(state),browser_hash,member_id,provider,app_id,action))
    return state


def consume_action_attempt(settings, provider, state, browser):
    if provider not in settings.providers:
        return None
    app_id=settings.providers[provider].identity_scope
    with core._transaction() as cur:
        cur.execute('''UPDATE richon.oauth_account_attempts SET consumed_at=CURRENT_TIMESTAMP
            WHERE state_hash=%s AND browser_hash=%s AND provider=%s AND app_id=%s
              AND consumed_at IS NULL AND expires_at>CURRENT_TIMESTAMP
            RETURNING member_id,action''',
            (core.token_digest(state),core.token_digest(browser),provider,app_id))
        row=cur.fetchone()
    return AccountAttempt(row[0],row[1],provider,app_id) if row else None


def finish_verified_action(settings, attempt, identity, browser):
    if (not isinstance(attempt,AccountAttempt) or identity.provider!=attempt.provider
            or identity.app_id!=attempt.app_id or attempt.provider not in settings.providers
            or settings.providers[attempt.provider].identity_scope!=attempt.app_id):
        raise AccountActionRejected()
    with core._transaction() as cur:
        cur.execute('SELECT status FROM richon.members WHERE member_id=%s FOR SHARE',(attempt.member_id,))
        member=cur.fetchone()
        if not member or member[0]!='active':
            raise core.MemberUnavailable()
        cur.execute('SELECT pg_advisory_xact_lock(%s)',
                    (_identity_lock(identity.provider,identity.app_id,identity.subject),))
        cur.execute('''SELECT member_id FROM richon.auth_identities
                       WHERE provider=%s AND app_id=%s AND subject=%s''',
                    (identity.provider,identity.app_id,identity.subject))
        owner=cur.fetchone()
        if attempt.action in ('reauth','unlink','withdraw'):
            if owner!=(attempt.member_id,):
                raise ProviderNotLinked()
            if attempt.action=='unlink':
                cur.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id=%s',(attempt.member_id,))
                if cur.fetchone()[0] <= 1:
                    raise LastLoginMethod()
            if attempt.action=='withdraw':
                cur.execute('''SELECT 1 FROM richon.account_withdrawals
                               WHERE member_id=%s AND expires_at>CURRENT_TIMESTAMP''',(attempt.member_id,))
                if cur.fetchone()!=(1,):
                    raise WithdrawalNotPrepared()
            return attempt.action,attempt.member_id,None
        if owner:
            if owner==(attempt.member_id,):
                raise AlreadyLinked()
            raise IdentityInUse()
        cur.execute('''SELECT 1 FROM richon.auth_identities
                       WHERE member_id=%s AND provider=%s AND app_id=%s''',
                    (attempt.member_id,identity.provider,identity.app_id))
        if cur.fetchone():
            raise AlreadyLinked()
        ticket=secrets.token_urlsafe(32)
        cur.execute('''DELETE FROM richon.oauth_link_confirmations
                       WHERE expires_at<CURRENT_TIMESTAMP OR member_id=%s OR browser_hash=%s''',
                    (attempt.member_id,core.token_digest(browser)))
        cur.execute('''INSERT INTO richon.oauth_link_confirmations
            (ticket_hash,browser_hash,member_id,provider,app_id,subject,expires_at)
            VALUES(%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP+interval '10 minutes')''',
            (core.token_digest(ticket),core.token_digest(browser),attempt.member_id,
             identity.provider,identity.app_id,identity.subject))
    return 'link',attempt.member_id,ticket


def pending_link(settings, ticket, browser, member_id):
    with core._transaction() as cur:
        cur.execute('''SELECT provider,app_id FROM richon.oauth_link_confirmations
            WHERE ticket_hash=%s AND browser_hash=%s AND member_id=%s
              AND expires_at>CURRENT_TIMESTAMP''',
            (core.token_digest(ticket),core.token_digest(browser),member_id))
        row=cur.fetchone()
    if not row:
        return None
    if row[0] not in settings.providers or settings.providers[row[0]].identity_scope!=row[1]:
        raise AccountActionRejected()
    return row[0]


def cancel_link(ticket, browser, member_id):
    with core._transaction() as cur:
        cur.execute('''DELETE FROM richon.oauth_link_confirmations
                       WHERE ticket_hash=%s AND browser_hash=%s AND member_id=%s''',
                    (core.token_digest(ticket),core.token_digest(browser),member_id))


def confirm_link(settings, ticket, browser, member_id):
    with core._transaction() as cur:
        cur.execute('''SELECT provider,app_id,subject FROM richon.oauth_link_confirmations
            WHERE ticket_hash=%s AND browser_hash=%s AND member_id=%s
              AND expires_at>CURRENT_TIMESTAMP''',
            (core.token_digest(ticket),core.token_digest(browser),member_id))
        row=cur.fetchone()
        if not row:
            raise AccountActionRejected()
        provider,app_id,subject=row
        if provider not in settings.providers or settings.providers[provider].identity_scope!=app_id:
            raise AccountActionRejected()
        cur.execute('SELECT status FROM richon.members WHERE member_id=%s FOR UPDATE',(member_id,))
        if cur.fetchone()!=('active',):
            raise core.MemberUnavailable()
        cur.execute('SELECT pg_advisory_xact_lock(%s)',(_identity_lock(provider,app_id,subject),))
        cur.execute('''SELECT member_id FROM richon.auth_identities
                       WHERE provider=%s AND app_id=%s AND subject=%s''',(provider,app_id,subject))
        owner=cur.fetchone()
        if owner and owner!=(member_id,):
            raise IdentityInUse()
        cur.execute('''SELECT 1 FROM richon.auth_identities
                       WHERE member_id=%s AND provider=%s AND app_id=%s''',(member_id,provider,app_id))
        existing=cur.fetchone()
        if not existing and not owner:
            cur.execute('''INSERT INTO richon.auth_identities(provider,app_id,subject,member_id)
                           VALUES(%s,%s,%s,%s)''',(provider,app_id,subject,member_id))
        elif not owner:
            raise AlreadyLinked()
        cur.execute('DELETE FROM richon.oauth_link_confirmations WHERE ticket_hash=%s',
                    (core.token_digest(ticket),))
    return providers_for(member_id,settings)


def record_unlink_failure(member_id, provider):
    if provider not in ('kakao','naver'):
        raise AccountActionRejected()
    with core._transaction() as cur:
        cur.execute('''DELETE FROM richon.provider_unlink_failures
                       WHERE expires_at<=CURRENT_TIMESTAMP OR (member_id=%s AND provider=%s)''',
                    (member_id,provider))
        cur.execute('''INSERT INTO richon.provider_unlink_failures
            (event_id,member_id,provider,safe_code) VALUES(%s,%s,%s,'provider_unavailable')''',
            (uuid4(),member_id,provider))


def _clear_unlink_failures(cur, member_id, provider):
    cur.execute('DELETE FROM richon.provider_unlink_failures WHERE member_id=%s AND provider=%s',
                (member_id,provider))


def unlink_failure_pending(member_id):
    with core._transaction() as cur:
        cur.execute('''SELECT 1 FROM richon.provider_unlink_failures
                       WHERE member_id=%s AND expires_at>CURRENT_TIMESTAMP LIMIT 1''',(member_id,))
        return cur.fetchone()==(1,)


def complete_unlink(settings, member_id, identity):
    with core._transaction() as cur:
        cur.execute('SELECT status FROM richon.members WHERE member_id=%s FOR UPDATE',(member_id,))
        if cur.fetchone()!=('active',):
            raise core.MemberUnavailable()
        cur.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id=%s',(member_id,))
        if cur.fetchone()[0] <= 1:
            raise LastLoginMethod()
        cur.execute('''DELETE FROM richon.oauth_signups
                       WHERE provider=%s AND app_id=%s AND subject=%s''',
                    (identity.provider,identity.app_id,identity.subject))
        cur.execute('''DELETE FROM richon.auth_identities
                       WHERE member_id=%s AND provider=%s AND app_id=%s AND subject=%s''',
                    (member_id,identity.provider,identity.app_id,identity.subject))
        if cur.rowcount!=1:
            raise ProviderNotLinked()
        _clear_unlink_failures(cur,member_id,identity.provider)
        cur.execute('UPDATE richon.members SET auth_version=auth_version+1 WHERE member_id=%s',(member_id,))
        cur.execute('''UPDATE richon.member_sessions SET revoked_at=CURRENT_TIMESTAMP
                       WHERE member_id=%s AND revoked_at IS NULL''',(member_id,))
        return _providers_cur(cur,member_id,settings)


def complete_withdraw_provider(settings, member_id, identity):
    with core._transaction() as cur:
        cur.execute('SELECT status FROM richon.members WHERE member_id=%s FOR UPDATE',(member_id,))
        if cur.fetchone()!=('active',):
            raise core.MemberUnavailable()
        cur.execute('''SELECT 1 FROM richon.account_withdrawals
                       WHERE member_id=%s AND expires_at>CURRENT_TIMESTAMP''',(member_id,))
        if cur.fetchone()!=(1,):
            raise WithdrawalNotPrepared()
        cur.execute('''DELETE FROM richon.oauth_signups
                       WHERE provider=%s AND app_id=%s AND subject=%s''',
                    (identity.provider,identity.app_id,identity.subject))
        cur.execute('''DELETE FROM richon.auth_identities
                       WHERE member_id=%s AND provider=%s AND app_id=%s AND subject=%s''',
                    (member_id,identity.provider,identity.app_id,identity.subject))
        if cur.rowcount!=1:
            raise ProviderNotLinked()
        _clear_unlink_failures(cur,member_id,identity.provider)
        return _providers_cur(cur,member_id,settings)


def finalize_withdrawal(member_id):
    """Erase normal account PII after every linked provider is externally unlinked.

    Transaction records required for retention are copied to a write-only
    retention table, then PII and its derived fingerprint are scrubbed from the
    operational order row and the normal member-order link is removed.
    """
    with core._transaction() as cur:
        cur.execute('SELECT role,status FROM richon.members WHERE member_id=%s FOR UPDATE',(member_id,))
        row=cur.fetchone()
        if not row or row[1]!='active':
            raise core.MemberUnavailable()
        if row[0]=='admin':
            raise AdminWithdrawalNotAllowed()
        cur.execute('''SELECT 1 FROM richon.account_withdrawals
                       WHERE member_id=%s AND expires_at>CURRENT_TIMESTAMP''',(member_id,))
        if cur.fetchone()!=(1,):
            raise WithdrawalNotPrepared()
        cur.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id=%s',(member_id,))
        if cur.fetchone()[0] != 0:
            raise LifecycleNotReady()
        cur.execute("SELECT to_regclass('richon.enrollment_learners') IS NOT NULL")
        if cur.fetchone()==(True,):
            cur.execute('''UPDATE richon.enrollment_learners
                           SET member_id=NULL,name=%s,nickname=NULL,email=NULL,phone=NULL
                           WHERE member_id=%s''',('탈퇴 회원',member_id))
        cur.execute('''SELECT o.order_id,o.course_id,o.course_title,o.cohort,o.amount_krw,
                              o.currency,o.status,o.customer_name,o.customer_phone,
                              o.customer_email,o.created_at
                       FROM richon.member_order_links l
                       JOIN richon.orders o USING(order_id)
                       WHERE l.member_id=%s ORDER BY o.order_id FOR UPDATE OF o''',(member_id,))
        retained=cur.fetchall()
        for order in retained:
            (order_id,course_id,course_title,cohort,amount,currency,status,
             customer_name,customer_phone,customer_email,created_at)=order
            cur.execute('''INSERT INTO richon.retained_order_records
                (order_id,member_id,course_id,course_title,cohort,amount_krw,currency,status,
                 customer_name,customer_phone,customer_email,order_created_at,expires_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s+interval '5 years')''',
                (order_id,member_id,course_id,course_title,cohort,amount,currency,status,
                 customer_name,customer_phone,customer_email,created_at,created_at))
            scrub=hashlib.sha256(('withdrawn:'+order_id).encode()).hexdigest()
            cur.execute('''UPDATE richon.orders
                           SET request_fingerprint=%s,customer_name=%s,
                               customer_phone=%s,customer_email=%s
                           WHERE order_id=%s''',
                        (scrub,'탈퇴 회원','01000000000','withdrawn@invalid.local',order_id))
        cur.execute('DELETE FROM richon.member_order_links WHERE member_id=%s',(member_id,))
        cur.execute('DELETE FROM richon.oauth_account_attempts WHERE member_id=%s',(member_id,))
        cur.execute('DELETE FROM richon.oauth_link_confirmations WHERE member_id=%s',(member_id,))
        cur.execute('DELETE FROM richon.provider_unlink_failures WHERE member_id=%s',(member_id,))
        cur.execute('DELETE FROM richon.member_sessions WHERE member_id=%s',(member_id,))
        cur.execute('DELETE FROM richon.member_profiles WHERE member_id=%s',(member_id,))
        cur.execute('DELETE FROM richon.account_withdrawals WHERE member_id=%s',(member_id,))
        cur.execute('''UPDATE richon.members
                       SET display_name=%s,status='withdrawn',withdrawn_at=CURRENT_TIMESTAMP,
                           auth_version=auth_version+1 WHERE member_id=%s''',
                    ('탈퇴 회원',member_id))
    return len(retained)
