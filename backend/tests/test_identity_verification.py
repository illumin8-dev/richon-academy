"""PortOne V2 identity verification boundary; synthetic responses only."""
import httpx
import pytest
import identity_verification as verification


def cfg():
    return verification.Settings(
        'store-12345678',
        'channel-key-12345678',
        'synthetic-secret-value-1234567890',
    )


def test_settings_are_disabled_by_default_and_secret_is_not_repr(monkeypatch):
    monkeypatch.delenv('RICHON_IDENTITY_VERIFICATION_ENABLED', raising=False)
    assert verification.enabled() is False
    assert 'synthetic-secret' not in repr(cfg())
    with pytest.raises(ValueError):
        verification.Settings('bad', 'channel-key-12345678', 'x'*32)


def test_browser_binding_is_signup_ticket_and_browser_specific():
    settings=cfg()
    browser='B'*43
    ticket='T'*43
    identity_id=verification.new_id()
    binding=verification.bind(settings,browser,ticket,identity_id)
    assert verification.require_bound(settings,browser,ticket,binding,identity_id)==identity_id
    with pytest.raises(verification.VerificationRejected):
        verification.require_bound(settings,'C'*43,ticket,binding,identity_id)
    with pytest.raises(verification.VerificationRejected):
        verification.require_bound(settings,browser,'U'*43,binding,identity_id)
    with pytest.raises(verification.VerificationRejected):
        verification.require_bound(settings,browser,ticket,binding,verification.new_id())


def test_server_rechecks_verified_status_and_hashes_ci(monkeypatch):
    raw_ci='synthetic-portone-ci-value-1234567890'
    seen={}
    def respond(request):
        seen['url']=str(request.url)
        seen['authorization']=request.headers.get('Authorization')
        return httpx.Response(200,json={
            'status':'VERIFIED',
            'verifiedCustomer':{'ci':raw_ci,'name':'개인정보 예시'}
        })
    monkeypatch.setattr(
        verification,'_client',
        lambda:httpx.Client(transport=httpx.MockTransport(respond),
                            timeout=8,follow_redirects=False,trust_env=False))
    identity_id=verification.new_id()
    person=verification.verify(cfg(),identity_id)
    assert person.ci_digest!=raw_ci and len(person.ci_digest)==64
    assert raw_ci not in repr(person)
    assert seen['url'].endswith('/identity-verifications/'+identity_id)
    assert seen['authorization'].startswith('PortOne ')


@pytest.mark.parametrize('payload',[
    {'status':'READY'},
    {'status':'FAILED'},
    {'status':'VERIFIED','verifiedCustomer':{}},
    {'status':'VERIFIED','verifiedCustomer':{'ci':'short'}},
])
def test_unverified_or_missing_ci_fails_closed(monkeypatch,payload):
    monkeypatch.setattr(
        verification,'_client',
        lambda:httpx.Client(
            transport=httpx.MockTransport(lambda _request:httpx.Response(200,json=payload)),
            timeout=8,follow_redirects=False,trust_env=False))
    with pytest.raises(verification.VerificationRejected):
        verification.verify(cfg(),verification.new_id())
