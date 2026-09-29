"""Shared short notice and explicit first-registration form; no tracking scripts."""
from html import escape as e
import re
from member_profile import AGE_RANGES, VERSION
import marketing_consent as marketing


def notice(settings):
    marketing_row = (
        '<tr><td>선택 / 광고성 정보 수신 동의 (문자·이메일)</td>'
        '<td>강의, 특강, 이벤트 및 혜택 안내</td></tr>'
        if marketing.enabled() else '')
    marketing_note = (
        '<p>광고성 정보 수신은 선택사항이며 동의하지 않아도 기본 회원 서비스를 이용할 수 있습니다. '
        '동의 후에도 마이페이지에서 철회할 수 있습니다.</p>'
        if marketing.enabled() else
        '<p>전화·이메일의 입력은 실명·휴대전화 본인인증을 의미하지 않습니다. '
        '홍보 수신에는 별도의 동의가 필요합니다.</p>')
    return f'''<details class="collection-notice"><summary>회원 관리와 상담에 필요한 정보를 수집합니다. <span>수집·이용 안내</span></summary>
<table><caption>회원가입 개인정보 수집·이용 안내</caption><thead><tr><th>구분 / 항목</th><th>목적</th></tr></thead><tbody>
<tr><td>필수 / 간편로그인 제공자·앱별 회원 식별정보</td><td>회원 식별 및 계정 관리</td></tr>
<tr><td>필수 / 이름</td><td>회원 확인, 수강생 관리 및 상담 대상 확인</td></tr>
<tr><td>필수 / 휴대전화번호</td><td>회원 서비스 안내 및 상담 연락</td></tr>
<tr><td>필수 / 이메일</td><td>회원 서비스 안내 및 강의자료 발송</td></tr>
<tr><td>필수(카카오 회원가입 시) / CI(연계정보)</td><td>동일인의 중복 회원가입 방지 및 기존 회원 비교 식별</td></tr>
<tr><td>선택 / 연령대·성별</td><td>생애주기와 주거 수요를 고려한 맞춤 상담 준비 및 상담 우선순위 설정</td></tr>
<tr><td>필수 / 만 14세 이상 자기확인 여부, 동의 버전·시점</td><td>가입 대상 및 동의 내역 확인</td></tr>
{marketing_row}</tbody></table>
<p>회원정보는 탈퇴 시까지, 선택 상담정보는 동의 철회 또는 탈퇴 시까지 보유합니다. 법령에 따라 보존할 거래기록은 해당 정보만 분리 보관합니다.</p>
<p>동의를 거부할 수 있습니다. 필수 수집·이용에 동의하지 않으면 회원가입을 할 수 없으며, 선택정보 제공에 동의하지 않아도 기본 회원 서비스를 이용할 수 있습니다.</p>
{marketing_note}
<p><a href="{e(settings.terms_url)}" target="_blank" rel="noopener noreferrer">이용약관</a> / <a href="{e(settings.privacy_url)}" target="_blank" rel="noopener noreferrer">개인정보처리방침</a></p></details>'''


def _display_phone(value):
    if not isinstance(value, str):
        return ''
    if re.fullmatch(r'01[016789][0-9]{8}', value):
        return value[:3] + '-' + value[3:7] + '-' + value[7:]
    if re.fullmatch(r'01[016789][0-9]{7}', value):
        return value[:3] + '-' + value[3:6] + '-' + value[6:]
    return value


def signup_form(settings, csrf, provider_profile=None, provider=None):
    provider_profile = provider_profile or type('EmptyProfile', (), {
        'name':None,'phone':None,'email':None,'age_range':None,'gender':None,'ci_digest':None})()

    marketing_input = (
        '<label class="auth-check-row"><input type="checkbox" name="marketing" value="yes" data-consent-item> '
        '<span><strong>광고성 정보 수신</strong> <span class="auth-optional">선택</span><br><small>문자·이메일로 강의 / 특강 / 이벤트 소식을 받습니다.</small></span></label>'
        if marketing.enabled() else '')

    placeholders = {
        'name':'리치온',
        'phone':'010-0000-0000',
        'email':'richon@academy.com',
    }

    def field(name, label, value, *, kind='text', autocomplete='', maxlength=''):
        locked = isinstance(value, str) and bool(value)
        display = _display_phone(value) if name == 'phone' else (value or '')
        attrs = [
            f'name="{name}"', f'type="{kind}"', f'autocomplete="{autocomplete}"',
            f'value="{e(display)}"', f'placeholder="{e(placeholders[name])}"', 'required'
        ]
        if maxlength:
            attrs.append(f'maxlength="{maxlength}"')
        if locked:
            attrs.extend(['readonly', 'aria-readonly="true"', 'data-provider-locked="true"'])
        badge = '<span class="provider-lock-badge">확인됨</span>' if locked else ''
        return (
            '<label class="auth-field"><span class="auth-field-head">'
            f'<span class="auth-field-meta">{e(label)} <span class="auth-required">필수</span></span>{badge}'
            f'</span><input {" ".join(attrs)}></label>'
        )

    def optional_select(name, label, values, selected):
        locked = selected in values
        options = ['<option value="">선택하지 않음</option>']
        for value, text in values.items():
            mark = ' selected' if value == selected else ''
            options.append(f'<option value="{e(value)}"{mark}>{e(text)}</option>')
        attrs = [f'id="signup-{name}"', 'data-optional-profile="true"']
        if locked:
            attrs.extend(['disabled', 'aria-disabled="true"', 'data-provider-locked="true"'])
        else:
            attrs.append(f'name="{name}"')
        hidden = f'<input type="hidden" name="{name}" value="{e(selected)}">' if locked else ''
        badge = '<span class="provider-lock-badge">확인됨</span>' if locked else ''
        return (
            '<label class="auth-field"><span class="auth-field-head">'
            f'<span class="auth-field-meta">{e(label)} <span class="auth-optional">선택</span></span>{badge}'
            f'</span><select {" ".join(attrs)}>{"".join(options)}</select>{hidden}</label>'
        )

    age_values = {
        age: ('14~19세' if age == '14-19' else ('70세 이상' if age == '70+' else age.replace('-', '~') + '세'))
        for age in AGE_RANGES
    }
    gender_values = {'female':'여성','male':'남성'}

    ci_block = ''
    ci_ready = True
    if provider == 'kakao':
        ci_ready = isinstance(provider_profile.ci_digest, str) and bool(provider_profile.ci_digest)
        state = '확인됨' if ci_ready else '확인 필요'
        klass = 'auth-ci-card' if ci_ready else 'auth-ci-card pending'
        ci_block = (
            f'<div class="{klass}"><div><strong>CI(연계정보) <span class="auth-required">필수 / 카카오</span></strong>'
            '<small>동일인의 중복 회원가입 방지 및 기존 회원 비교 식별에만 사용합니다.</small></div>'
            f'<span class="provider-lock-badge">{state}</span></div>'
        )
        if not ci_ready:
            ci_block += '<p class="auth-ci-warning" role="alert">카카오 CI 확인 후 가입을 완료할 수 있습니다.</p>'

    disabled = ' disabled aria-disabled="true"' if not ci_ready else ''

    return f'''<p class="auth-intro">회원정보를 확인해 주세요.</p>{notice(settings)}
<form method="post" action="/auth/signup" data-richon-signup>
<input type="hidden" name="csrf" value="{e(csrf)}">
<input type="hidden" name="terms_version" value="{VERSION}">
<input type="hidden" name="privacy_version" value="{VERSION}">
<div class="auth-profile-grid">
{field('name','이름',provider_profile.name,autocomplete='name',maxlength='80')}
{field('phone','휴대전화번호',provider_profile.phone,kind='tel',autocomplete='tel',maxlength='32')}
{field('email','이메일',provider_profile.email,kind='email',autocomplete='email',maxlength='254')}
</div>
{ci_block}
<div class="auth-consent-all"><label class="auth-check-row"><input id="consent-all" type="checkbox" data-consent-all> <span><strong>전체 동의</strong> <small>(선택 항목 포함)</small></span></label></div>
<fieldset class="auth-consultation"><legend>상담정보 <span class="auth-optional">선택</span></legend>
<div class="auth-consultation-grid">
{optional_select('age_range','연령대',age_values,provider_profile.age_range)}
{optional_select('gender','성별',gender_values,provider_profile.gender)}
</div>
<label class="auth-check-row"><input type="checkbox" name="consultation" value="yes" data-consent-item> <span>상담정보 수집·이용 동의</span></label>
<p class="auth-field-help">연령대·성별은 동의한 경우에만 상담정보로 저장합니다.</p></fieldset>
<div class="auth-consent-list">
<label class="auth-check-row"><input type="checkbox" name="over14" value="yes" required data-consent-item> <span><strong>만 14세 이상</strong> <span class="auth-required">필수</span></span></label>
<label class="auth-check-row"><input type="checkbox" name="terms" value="yes" required data-consent-item> <span><a href="{e(settings.terms_url)}" target="_blank" rel="noopener noreferrer">이용약관</a> 동의 <span class="auth-required">필수</span></span></label>
<label class="auth-check-row"><input type="checkbox" name="privacy" value="yes" required data-consent-item> <span>개인정보 수집·이용 동의 <span class="auth-required">필수</span></span></label>
{marketing_input}
</div>
<p class="auth-consent-help">전체 동의 후에도 선택 항목은 개별 해제할 수 있습니다.</p>
<button type="submit"{disabled}>동의하고 가입 완료</button></form>'''
