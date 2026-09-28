"""New signup SQL, only through existing guarded disposable loopback fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4
import os
import secrets
import pytest
import auth_core as core
import member_profile as profile
import member_profile_migrate as migration
import oauth_signup_profile_migrate as provider_migration
import oauth_signup_demographics_migrate as demographic_migration
import kakao_ci_migrate as ci_migration
import oauth_providers as providers
import member_profile_store as registration
import oauth_store as tickets
import portal_migrate
import portal_store
from test_orders_postgres import postgres
from test_auth_postgres import guarded_target, auth_postgres, CONSENT
from test_oauth_postgres import oauth_db
from test_member_profile import cfg, data

pytestmark = pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB') != 'YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


@pytest.fixture(scope='module')
def profile_db(oauth_db):
    assert portal_migrate.apply_migration()
    assert migration.apply_migration()
    assert provider_migration.apply_migration() is False
    assert demographic_migration.apply_migration() is False
    assert ci_migration.apply_migration() is False
    return oauth_db


def pending(provider='naver', identity=None):
    settings = cfg()
    identity = identity or core.VerifiedIdentity(provider, settings.providers[provider].identity_scope, uuid4().hex, '회원')
    browser = secrets.token_urlsafe(32)
    provider_profile = None
    if identity.provider == 'kakao':
        provider_profile = providers.ProviderProfile(ci_digest=core.token_digest(secrets.token_urlsafe(32)))
    return identity, browser, tickets.stage_signup(settings, identity, browser, '/portal/mypage', provider_profile)


def save(identity=None, **fields):
    identity, browser, ticket = pending(identity=identity)
    result = registration.finish(cfg(), ticket, browser, profile.Registration.from_form({**data(), **fields}))
    return result[0]


def test_migration_reentry_and_no_public_access(profile_db):
    assert migration.apply_migration() is False
    assert provider_migration.apply_migration() is False
    with profile_db() as c:
        assert c.execute("SELECT count(*) FROM richon.schema_migrations WHERE version='009_member_profiles'").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM richon.schema_migrations WHERE version='012_oauth_signup_provider_profile'").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM richon.schema_migrations WHERE version='013_oauth_signup_provider_demographics'").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM richon.schema_migrations WHERE version='014_kakao_ci_dedup'").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM pg_class t, LATERAL aclexplode(t.relacl) a WHERE t.oid='richon.member_profiles'::regclass AND a.grantee=0").fetchone() == (0,)


@pytest.mark.parametrize('consent', [False, True])
def test_profile_and_consent_persist_together(profile_db, consent):
    identity, browser, ticket = pending()
    fields = {**data(), 'age_range':'30-39', 'gender':'female'}
    if consent:
        fields['consultation'] = 'yes'
    mid, target = registration.finish(cfg(), ticket, browser, profile.Registration.from_form(fields))
    assert target == '/portal/mypage' and registration.completed(mid, cfg())
    with profile_db() as c:
        row = c.execute('SELECT name,phone,email,age_range,gender,consultation_consent,over14_confirmed,terms_version,privacy_version,consented_at IS NOT NULL FROM richon.member_profiles WHERE member_id=%s', (mid,)).fetchone()
        assert row == ('테스트 이름','01012345678','tester@example.invalid', '30-39' if consent else None, 'female' if consent else None, consent, True, profile.VERSION, profile.VERSION, True)
        assert c.execute('SELECT 1 FROM richon.oauth_signups WHERE ticket_hash=%s', (core.token_digest(ticket),)).fetchone() is None
        assert c.execute('SELECT display_name,role FROM richon.members WHERE member_id=%s', (mid,)).fetchone() == ('테스트 이름','member')


def test_existing_account_keeps_identity_role_and_old_rows(profile_db):
    identity, _, _ = pending()
    mid = core.register_verified_identity(identity, CONSENT)
    with profile_db() as c:
        before = c.execute('SELECT * FROM richon.members WHERE member_id=%s', (mid,)).fetchone()
    assert save(identity) == mid
    with profile_db() as c:
        assert c.execute('SELECT * FROM richon.members WHERE member_id=%s', (mid,)).fetchone() == before
    # Duplicate successful provider callback cannot overwrite accepted data.
    assert save(identity, name='다른 이름') == mid
    with profile_db() as c:
        assert c.execute('SELECT name FROM richon.member_profiles WHERE member_id=%s', (mid,)).fetchone() == ('테스트 이름',)


def test_same_kakao_ci_cannot_create_second_member(profile_db):
    settings=cfg();ci=core.token_digest(secrets.token_urlsafe(32))
    one=core.VerifiedIdentity('kakao',settings.providers['kakao'].identity_scope,uuid4().hex,'회원1')
    two=core.VerifiedIdentity('kakao',settings.providers['kakao'].identity_scope,uuid4().hex,'회원2')
    browser1=secrets.token_urlsafe(32)
    ticket1=tickets.stage_signup(settings,one,browser1,'/portal/mypage',providers.ProviderProfile(ci_digest=ci))
    first,_=registration.finish(settings,ticket1,browser1,profile.Registration.from_form(data()))
    browser2=secrets.token_urlsafe(32)
    ticket2=tickets.stage_signup(settings,two,browser2,'/portal/mypage',providers.ProviderProfile(ci_digest=ci))
    with pytest.raises(tickets.InvalidFlow):
        registration.finish(settings,ticket2,browser2,profile.Registration.from_form(data()))
    with profile_db() as conn:
        assert conn.execute('SELECT member_id FROM richon.member_ci_claims WHERE ci_digest=%s',(ci,)).fetchone()==(first,)
        assert conn.execute('SELECT count(*) FROM richon.auth_identities WHERE member_id<>%s AND provider=%s',
                            (first,'kakao')).fetchone()==(0,)


def test_kakao_signup_requires_ci(profile_db):
    settings=cfg();identity=core.VerifiedIdentity('kakao',settings.providers['kakao'].identity_scope,uuid4().hex,'회원')
    browser=secrets.token_urlsafe(32)
    ticket=tickets.stage_signup(settings,identity,browser,'/portal/mypage',providers.ProviderProfile())
    with pytest.raises(tickets.InvalidFlow):
        registration.finish(settings,ticket,browser,profile.Registration.from_form(data()))


def test_same_contacts_different_provider_not_merged(profile_db):
    a, _, _ = pending('naver')
    b, _, _ = pending('kakao')
    assert save(a) != save(b)


def test_provider_profile_overrides_tampered_locked_signup_fields(profile_db):
    settings=cfg();identity=core.VerifiedIdentity('naver',settings.providers['naver'].identity_scope,uuid4().hex,'제공자 이름')
    browser=secrets.token_urlsafe(32)
    locked=providers.ProviderProfile('제공자 이름','01022223333','provider@example.invalid','30-39','female')
    ticket=tickets.stage_signup(settings,identity,browser,'/portal/mypage',locked)
    submitted=profile.Registration('변조 이름','01099998888','tampered@example.invalid','40-49','male',True,True)
    mid,_=registration.finish(settings,ticket,browser,submitted)
    with profile_db() as conn:
        assert conn.execute('SELECT name,phone,email,age_range,gender FROM richon.member_profiles WHERE member_id=%s',(mid,)).fetchone()==(
            '제공자 이름','01022223333','provider@example.invalid','30-39','female')


def test_provider_demographics_discarded_without_consultation_consent(profile_db):
    settings=cfg();identity=core.VerifiedIdentity('naver',settings.providers['naver'].identity_scope,uuid4().hex,'제공자 이름')
    browser=secrets.token_urlsafe(32)
    ticket=tickets.stage_signup(settings,identity,browser,'/portal/mypage',
                                providers.ProviderProfile(name='제공자 이름',age_range='30-39',gender='female'))
    submitted=profile.Registration('변조 이름','01033334444','user@example.invalid','40-49','male',False,True)
    mid,_=registration.finish(settings,ticket,browser,submitted)
    with profile_db() as conn:
        assert conn.execute('SELECT age_range,gender,consultation_consent FROM richon.member_profiles WHERE member_id=%s',(mid,)).fetchone()==(
            None,None,False)


def test_missing_provider_fields_remain_user_supplied(profile_db):
    settings=cfg();identity=core.VerifiedIdentity('naver',settings.providers['naver'].identity_scope,uuid4().hex,'회원')
    browser=secrets.token_urlsafe(32)
    ticket=tickets.stage_signup(settings,identity,browser,'/portal/mypage',
                                providers.ProviderProfile(name='제공자 이름'))
    submitted=profile.Registration('변조 이름','01033334444','user@example.invalid',None,None,False,True)
    mid,_=registration.finish(settings,ticket,browser,submitted)
    with profile_db() as conn:
        assert conn.execute('SELECT name,phone,email FROM richon.member_profiles WHERE member_id=%s',(mid,)).fetchone()==(
            '제공자 이름','01033334444','user@example.invalid')


def test_concurrent_tickets_one_member_and_profile(profile_db):
    identity, _, _ = pending()
    attempts = [pending(identity=identity)[1:] for _ in range(3)]
    barrier = Barrier(3)
    def submit(attempt):
        browser, ticket = attempt
        barrier.wait(timeout=10)
        return registration.finish(cfg(), ticket, browser, profile.Registration.from_form(data()))[0]
    with ThreadPoolExecutor(max_workers=3) as pool:
        members = list(pool.map(submit, attempts))
    assert len(set(members)) == 1
    with profile_db() as c:
        assert c.execute('SELECT count(*) FROM richon.member_profiles WHERE member_id=%s', (members[0],)).fetchone() == (1,)


def test_same_ticket_one_success(profile_db):
    identity, browser, ticket = pending()
    def submit(_):
        try:
            return registration.finish(cfg(), ticket, browser, profile.Registration.from_form(data()))
        except tickets.InvalidFlow:
            return None
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(submit, range(3)))
    assert sum(value is not None for value in results) == 1


def test_commit_failure_rolls_back_ticket_member_and_profile(profile_db):
    import psycopg
    identity, browser, ticket = pending()
    with profile_db() as c:
        c.execute("CREATE FUNCTION richon.profile_test_error() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic failure'; END; $$")
        c.execute('CREATE CONSTRAINT TRIGGER profile_test_error AFTER INSERT ON richon.member_profiles DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION richon.profile_test_error()')
    try:
        with pytest.raises(psycopg.errors.RaiseException):
            registration.finish(cfg(), ticket, browser, profile.Registration.from_form(data()))
        with profile_db() as c:
            assert c.execute('SELECT count(*) FROM richon.oauth_signups WHERE ticket_hash=%s', (core.token_digest(ticket),)).fetchone() == (1,)
            assert c.execute('SELECT count(*) FROM richon.auth_identities WHERE provider=%s AND app_id=%s AND subject=%s', (identity.provider,identity.app_id,identity.subject)).fetchone() == (0,)
    finally:
        with profile_db() as c:
            c.execute('DROP TRIGGER profile_test_error ON richon.member_profiles')
            c.execute('DROP FUNCTION richon.profile_test_error()')
    assert registration.finish(cfg(), ticket, browser, profile.Registration.from_form(data()))[1] == '/portal/mypage'


@pytest.mark.parametrize('case', ['browser','expired','policy','disabled'])
def test_invalid_context_does_not_write(profile_db, case):
    identity, browser, ticket = pending()
    settings = cfg()
    if case == 'browser':
        browser = secrets.token_urlsafe(32)
    elif case == 'policy':
        settings = replace(settings, terms_version='internal-test-v1', privacy_version='internal-test-v1')
    elif case == 'expired':
        with profile_db() as c:
            c.execute("UPDATE richon.oauth_signups SET expires_at=CURRENT_TIMESTAMP-interval '1 second' WHERE ticket_hash=%s", (core.token_digest(ticket),))
    else:
        mid = core.register_verified_identity(identity, CONSENT)
        with profile_db() as c:
            c.execute("UPDATE richon.members SET status='disabled' WHERE member_id=%s", (mid,))
    with pytest.raises((tickets.InvalidFlow, core.MemberUnavailable)):
        registration.finish(settings, ticket, browser, profile.Registration.from_form(data()))
    with profile_db() as c:
        assert c.execute('SELECT count(*) FROM richon.member_profiles p JOIN richon.auth_identities i USING(member_id) WHERE i.provider=%s AND i.app_id=%s AND i.subject=%s', (identity.provider,identity.app_id,identity.subject)).fetchone() == (0,)


def test_profile_required_for_old_session_and_own_view_only(profile_db, monkeypatch):
    identity, _, _ = pending()
    mid = core.register_verified_identity(identity, CONSENT)
    token = core.issue_session(mid).token
    monkeypatch.setenv('RICHON_TERMS_VERSION', profile.VERSION)
    monkeypatch.setenv('RICHON_PRIVACY_VERSION', profile.VERSION)
    with pytest.raises(core.AuthenticationRequired):
        core.resolve_session(token)
    assert save(identity) == mid
    assert core.resolve_session(token).display_name == '테스트 이름'
    other = save(name='별도 회원', email='other@example.invalid')
    own = portal_store.profile(mid)
    assert own['registration']['email'] == 'tester@example.invalid'
    assert portal_store.profile(other)['registration']['email'] == 'other@example.invalid'
    assert own['display_name'] == '테스트 이름'


def test_missing_migration_is_not_created_by_validation(profile_db):
    with profile_db() as c:
        c.execute('ALTER TABLE richon.member_profiles RENAME TO profile_hidden_for_test')
    try:
        with pytest.raises(Exception):
            registration.completed(uuid4(), cfg())
        with profile_db() as c:
            assert c.execute("SELECT to_regclass('richon.member_profiles')").fetchone() == (None,)
    finally:
        with profile_db() as c:
            c.execute('ALTER TABLE richon.profile_hidden_for_test RENAME TO member_profiles')
