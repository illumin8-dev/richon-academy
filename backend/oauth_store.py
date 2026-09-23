"""Short-lived browser-bound one-time OAuth transactions. Uses verified TLS DB."""
import secrets
from auth_core import _transaction,token_digest,VerifiedIdentity,MemberUnavailable
from oauth_providers import RETURNS

class InvalidFlow(Exception):
    pass


def begin(settings,provider,browser,return_to):
    if provider not in settings.providers or return_to not in RETURNS: raise InvalidFlow()
    state=secrets.token_urlsafe(32)
    with _transaction() as cur:
        cur.execute('DELETE FROM richon.oauth_attempts WHERE state_hash IN (SELECT state_hash FROM richon.oauth_attempts WHERE expires_at<CURRENT_TIMESTAMP ORDER BY expires_at LIMIT 100)')
        cur.execute('DELETE FROM richon.oauth_signups WHERE ticket_hash IN (SELECT ticket_hash FROM richon.oauth_signups WHERE expires_at<CURRENT_TIMESTAMP ORDER BY expires_at LIMIT 100)')
        cur.execute('''INSERT INTO richon.oauth_attempts(state_hash,browser_hash,provider,app_id,return_to,expires_at)
          VALUES(%s,%s,%s,%s,%s,CURRENT_TIMESTAMP+interval '5 minutes')''',
          (token_digest(state),token_digest(browser),provider,settings.providers[provider].identity_scope,return_to))
    return state


def consume_attempt(settings,provider,state,browser):
    if provider not in settings.providers: raise InvalidFlow()
    with _transaction() as cur:
        cur.execute('''UPDATE richon.oauth_attempts SET consumed_at=CURRENT_TIMESTAMP
          WHERE state_hash=%s AND browser_hash=%s AND provider=%s AND app_id=%s
           AND consumed_at IS NULL AND expires_at>CURRENT_TIMESTAMP RETURNING return_to''',
          (token_digest(state),token_digest(browser),provider,settings.providers[provider].identity_scope))
        row=cur.fetchone()
        if row is None or row[0] not in RETURNS: raise InvalidFlow()
    return row[0]


def member_for(identity):
    with _transaction() as cur:
        cur.execute('''SELECT m.member_id,m.status FROM richon.auth_identities i JOIN richon.members m USING(member_id)
           WHERE i.provider=%s AND i.app_id=%s AND i.subject=%s''',(identity.provider,identity.app_id,identity.subject))
        row=cur.fetchone()
        if row and row[1]!='active': raise MemberUnavailable()
    return row[0] if row else None


def stage_signup(settings,identity,browser,return_to):
    if (identity.provider not in settings.providers or identity.app_id != settings.providers[identity.provider].identity_scope
        or return_to not in RETURNS): raise InvalidFlow()
    ticket=secrets.token_urlsafe(32)
    with _transaction() as cur:
        cur.execute('DELETE FROM richon.oauth_signups WHERE browser_hash=%s',(token_digest(browser),))
        cur.execute('''INSERT INTO richon.oauth_signups
          (ticket_hash,browser_hash,provider,app_id,subject,display_name,return_to,terms_version,privacy_version,expires_at)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP+interval '10 minutes')''',
          (token_digest(ticket),token_digest(browser),identity.provider,identity.app_id,identity.subject,
           identity.display_name,return_to,settings.terms_version,settings.privacy_version))
    return ticket


def pending(settings,ticket,browser,*,consume=False):
    statement=('DELETE FROM richon.oauth_signups' if consume else 'SELECT provider,app_id,subject,display_name,return_to FROM richon.oauth_signups')
    statement+=' WHERE ticket_hash=%s AND browser_hash=%s AND expires_at>CURRENT_TIMESTAMP AND terms_version=%s AND privacy_version=%s'
    if consume: statement+=' RETURNING provider,app_id,subject,display_name,return_to'
    with _transaction() as cur:
        cur.execute(statement,(token_digest(ticket),token_digest(browser),settings.terms_version,settings.privacy_version))
        row=cur.fetchone()
        if not row or row[4] not in RETURNS: raise InvalidFlow()
        if row[0] not in settings.providers or settings.providers[row[0]].identity_scope!=row[1]: raise InvalidFlow()
    return VerifiedIdentity(*row[:4]),row[4]
