"""Static signup/login UX contract. No network, credentials, or customer data."""
from pathlib import Path
from types import SimpleNamespace

import signup_views

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'portal_static'


class Settings:
    terms_url='https://richonacademy.com/terms.html'
    privacy_url='https://richonacademy.com/privacy.html'


def profile(**overrides):
    values=dict(name=None,phone=None,email=None,age_range=None,gender=None,ci_digest=None)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_locked_provider_fields_use_visual_lock_without_long_explanation(monkeypatch):
    monkeypatch.setattr(signup_views.marketing,'enabled',lambda:True)
    html=signup_views.signup_form(
        Settings(),'a'*64,
        profile(name='김리치',phone='01029126056',email='richon@example.com',
                age_range='40-49',gender='male',ci_digest='b'*64),
        'kakao')
    assert html.count('data-provider-locked="true"') >= 5
    assert html.count('class="auth-lock-mark"') >= 6
    assert '소셜 계정에서 확인된 정보 / 가입 단계에서 수정할 수 없습니다.' not in html
    assert '소셜 계정에서 제공된 정보 / 선택 동의 시 상담정보로 저장됩니다.' not in html
    assert '010-2912-6056' in html
    assert 'auth-ci-status' in html and '확인됨' in html


def test_editable_fields_have_examples_and_phone_display_contract(monkeypatch):
    monkeypatch.setattr(signup_views.marketing,'enabled',lambda:False)
    html=signup_views.signup_form(Settings(),'a'*64,profile(),'naver')
    for value in ('placeholder="리치온"','placeholder="010-0000-0000"',
                  'placeholder="richon@academy.com"'):
        assert value in html
    assert signup_views.display_phone('01012345678')=='010-1234-5678'
    assert signup_views.display_phone('0101234567')=='010-123-4567'


def test_auth_assets_keep_modern_layout_and_auto_modal_contract():
    css=(STATIC/'auth.css').read_text()
    site=(STATIC/'site.css').read_text()
    signup=(STATIC/'signup.js').read_text()
    account=(STATIC/'account.js').read_text()
    for token in ('.auth-main{','.auth-field-locked','.auth-lock-mark','.auth-check-row',
                  '.auth-main .provider-login{width:min(100%,420px)'):
        assert token in css
    assert 'Auth fallback:' in site and 'max-width:620px' in site
    assert "formatPhone" in signup and "replace(/\\D/g,'')" in signup
    assert "loginPrompted:false" in account
    assert "queueMicrotask(()=>$('gate-login')?.click())" in account


def test_callback_diagnostic_is_stage_only():
    source=(ROOT/'oauth_http.py').read_text()
    assert "oauth_callback_failed stage=%s provider=%s" in source
    assert "stage='exchange_provider'" in source
    assert 'logger.exception' not in source
