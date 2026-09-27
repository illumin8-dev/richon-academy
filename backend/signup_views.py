"""Shared short notice and explicit first-registration form; no tracking scripts."""
from html import escape as e
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
<tr><td>선택 / 연령대·성별</td><td>생애주기와 주거 수요를 고려한 맞춤 상담 준비 및 상담 우선순위 설정</td></tr>
<tr><td>필수 / 만 14세 이상 자기확인 여부, 동의 버전·시점</td><td>가입 대상 및 동의 내역 확인</td></tr>
{marketing_row}</tbody></table>
<p>회원정보는 탈퇴 시까지, 선택 상담정보는 동의 철회 또는 탈퇴 시까지 보유합니다. 법령에 따라 보존할 거래기록은 해당 정보만 분리 보관합니다.</p>
<p>동의를 거부할 수 있습니다. 필수 수집·이용에 동의하지 않으면 회원가입을 할 수 없으며, 선택정보 제공에 동의하지 않아도 기본 회원 서비스를 이용할 수 있습니다.</p>
{marketing_note}
<p><a href="{e(settings.terms_url)}" target="_blank" rel="noopener noreferrer">이용약관</a> / <a href="{e(settings.privacy_url)}" target="_blank" rel="noopener noreferrer">개인정보처리방침</a></p></details>'''


def signup_form(settings, csrf, provider_profile=None):
    options = '<option value="">선택하지 않음</option>' + ''.join(
        f'<option value="{age}">{"14~19세" if age == "14-19" else age.replace("-", "~") + "세"}</option>' for age in AGE_RANGES)
    provider_profile = provider_profile or type('EmptyProfile', (), {'name':None,'phone':None,'email':None})()

    def field(name, label, value, *, kind='text', autocomplete='', maxlength=''):
        locked = isinstance(value, str) and bool(value)
        attrs = [
            f'name="{name}"', f'type="{kind}"', f'autocomplete="{autocomplete}"',
            f'value="{e(value or "")}"', 'required'
        ]
        if maxlength:
            attrs.append(f'maxlength="{maxlength}"')
        if locked:
            attrs.extend(['readonly', 'aria-readonly="true"', 'data-provider-locked="true"'])
        suffix = '<span class="provider-locked-note">소셜 계정에서 확인된 정보 / 가입 단계에서 수정할 수 없습니다.</span>' if locked else ''
        return f'<label>{label} [필수]<input {" ".join(attrs)}>{suffix}</label>'

    return f'''<p>회원정보를 확인해 주세요. 기존 계정은 그대로 유지됩니다.</p>{notice(settings)}
<form method="post" action="/auth/signup">
<input type="hidden" name="csrf" value="{e(csrf)}">
<input type="hidden" name="terms_version" value="{VERSION}">
<input type="hidden" name="privacy_version" value="{VERSION}">
{field('name','이름',provider_profile.name,autocomplete='name',maxlength='80')}
{field('phone','휴대전화번호',provider_profile.phone,kind='tel',autocomplete='tel',maxlength='32')}
{field('email','이메일',provider_profile.email,kind='email',autocomplete='email',maxlength='254')}
<fieldset><legend>상담정보 [선택]</legend>
<label>연령대<select name="age_range">{options}</select></label>
<label>성별<select name="gender"><option value="">선택하지 않음</option><option value="female">여성</option><option value="male">남성</option></select></label>
<label><input type="checkbox" name="consultation" value="yes"> [선택] 상담정보 수집·이용 동의</label>
<p>선택 동의가 없으면 입력한 연령대·성별은 저장하지 않습니다.</p></fieldset>
<label><input type="checkbox" name="over14" value="yes" required> [필수] 만 14세 이상입니다.</label>
<label><input type="checkbox" name="terms" value="yes" required> [필수] <a href="{e(settings.terms_url)}" target="_blank" rel="noopener noreferrer">이용약관</a> 동의</label>
<label><input type="checkbox" name="privacy" value="yes" required> [필수] 개인정보 수집·이용 동의</label>
<button type="submit">동의하고 가입 완료</button></form>'''
