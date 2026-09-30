"""Shared short notice and explicit first-registration form; no tracking scripts."""
from html import escape as e
from member_profile import AGE_RANGES, VERSION
import marketing_consent as marketing


def display_phone(value):
    if not isinstance(value, str):
        return value
    digits=''.join(ch for ch in value if ch.isdigit())
    if len(digits)==11 and digits.startswith('01'):
        return digits[:3]+'-'+digits[3:7]+'-'+digits[7:]
    if len(digits)==10 and digits.startswith('01'):
        return digits[:3]+'-'+digits[3:6]+'-'+digits[6:]
    return value


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


def signup_form(settings, csrf, provider_profile=None, provider=None):
    provider_profile = provider_profile or type('EmptyProfile', (), {
        'name':None,'phone':None,'email':None,'age_range':None,'gender':None,'ci_digest':None})()
    marketing_input = (
        '<label class="auth-check-row"><input type="checkbox" name="marketing" value="yes" data-consent-item> '
        '<span><strong>선택</strong> 광고성 정보 수신 동의 <small>문자 / 이메일</small></span></label>'
        if marketing.enabled() else '')

    def field(name, label, value, *, kind='text', autocomplete='', maxlength='', placeholder=''):
        locked = isinstance(value, str) and bool(value)
        shown = display_phone(value) if name == 'phone' else value
        attrs = [
            f'name="{name}"', f'type="{kind}"', f'autocomplete="{autocomplete}"',
            f'value="{e(shown or "")}"', 'required', 'class="auth-input"'
        ]
        if maxlength:
            attrs.append(f'maxlength="{maxlength}"')
        if placeholder and not locked:
            attrs.append(f'placeholder="{e(placeholder)}"')
        if locked:
            attrs.extend(['readonly', 'aria-readonly="true"', 'data-provider-locked="true"'])
        lock = '<span class="auth-lock-mark" aria-hidden="true"></span>' if locked else ''
        cls = 'auth-field auth-field-locked' if locked else 'auth-field'
        return (f'<label class="{cls}"><span class="auth-field-label">{label} '
                f'<em>필수</em></span><span class="auth-input-wrap">'
                f'<input {" ".join(attrs)}>{lock}</span></label>')

    def optional_select(name, label, values, selected):
        locked = selected in values
        options = ['<option value="">선택하지 않음</option>']
        for value, text in values.items():
            mark = ' selected' if value == selected else ''
            options.append(f'<option value="{e(value)}"{mark}>{e(text)}</option>')
        attrs = [f'id="signup-{name}"', 'class="auth-input"']
        if locked:
            attrs.extend(['disabled', 'aria-disabled="true"', 'data-provider-locked="true"'])
        else:
            attrs.append(f'name="{name}"')
        hidden = f'<input type="hidden" name="{name}" value="{e(selected)}">' if locked else ''
        lock = '<span class="auth-lock-mark" aria-hidden="true"></span>' if locked else ''
        cls = 'auth-field auth-field-locked' if locked else 'auth-field'
        return (f'<label class="{cls}"><span class="auth-field-label">{label} <em>선택</em></span>'
                f'<span class="auth-input-wrap"><select {" ".join(attrs)}>{"".join(options)}</select>'
                f'{lock}</span>{hidden}</label>')

    age_values = {
        age: ('14~19세' if age == '14-19' else ('70세 이상' if age == '70+' else age.replace('-', '~') + '세'))
        for age in AGE_RANGES
    }
    gender_values = {'female':'여성','male':'남성'}

    return f'''<p class="auth-intro">회원정보를 확인하고 가입을 완료해 주세요.</p>{notice(settings)}
<form method="post" action="/auth/signup" data-richon-signup class="signup-form">
<input type="hidden" name="csrf" value="{e(csrf)}">
<input type="hidden" name="terms_version" value="{VERSION}">
<input type="hidden" name="privacy_version" value="{VERSION}">
<section class="auth-form-section" aria-labelledby="signup-basic-title">
<h2 id="signup-basic-title">기본 정보</h2>
<div class="auth-field-grid">
{field('name','이름',provider_profile.name,autocomplete='name',maxlength='80',placeholder='리치온')}
{field('phone','휴대전화번호',provider_profile.phone,kind='tel',autocomplete='tel',maxlength='32',placeholder='010-0000-0000')}
{field('email','이메일',provider_profile.email,kind='email',autocomplete='email',maxlength='254',placeholder='richon@academy.com')}
</div>
{('<div class="auth-ci-status"><span class="auth-lock-mark" aria-hidden="true"></span><div><strong>CI(연계정보)</strong><small>카카오 제공 / 중복가입 방지와 기존 회원 비교 식별에만 사용</small></div><span class="auth-provider-badge">' + ('확인됨' if provider_profile.ci_digest else '확인 필요') + '</span></div>' if provider == 'kakao' else '')}
</section>
<section class="auth-form-section" aria-labelledby="signup-consult-title">
<div class="auth-section-heading"><div><h2 id="signup-consult-title">상담 정보</h2><p>선택 동의 시에만 저장됩니다.</p></div><span class="auth-optional-badge">선택</span></div>
<div class="auth-field-grid auth-field-grid-two">
{optional_select('age_range','연령대',age_values,provider_profile.age_range)}
{optional_select('gender','성별',gender_values,provider_profile.gender)}
</div>
<label class="auth-check-row"><input type="checkbox" name="consultation" value="yes" data-consent-item><span><strong>선택</strong> 상담정보 수집·이용 동의</span></label>
</section>
<section class="auth-form-section auth-consent-section" aria-labelledby="signup-consent-title">
<div class="auth-section-heading"><div><h2 id="signup-consent-title">약관 동의</h2></div></div>
<label class="auth-check-row auth-check-all"><input id="consent-all" type="checkbox" data-consent-all><span><strong>전체 동의</strong><small>선택 항목 포함</small></span></label>
<label class="auth-check-row"><input type="checkbox" name="over14" value="yes" required data-consent-item><span><strong>필수</strong> 만 14세 이상입니다.</span></label>
<label class="auth-check-row"><input type="checkbox" name="terms" value="yes" required data-consent-item><span><strong>필수</strong> <a href="{e(settings.terms_url)}" target="_blank" rel="noopener noreferrer">이용약관</a> 동의</span></label>
<label class="auth-check-row"><input type="checkbox" name="privacy" value="yes" required data-consent-item><span><strong>필수</strong> 개인정보 수집·이용 동의</span></label>
{marketing_input}
<p class="auth-consent-note">전체 동의 후에도 선택 항목은 개별적으로 해제할 수 있습니다.</p>
</section>
<button class="auth-submit" type="submit">동의하고 가입 완료</button>
</form>'''

