"""Static public UI contract checks; no network, credentials, or deployment."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
index=(ROOT/'index.html').read_text()
apply=(ROOT/'apply.html').read_text()
shared=ROOT/'frontend'/'shared'
work=(ROOT/'CURRENT_WORK.md').read_text()

def wrapped(name):
    value=(shared/(name+'.html')).read_text().strip()
    return '<!-- richon:shared-'+name+' -->\n'+value+'\n<!-- /richon:shared-'+name+' -->'

for page in (index,apply):
    assert wrapped('header') in page
    assert wrapped('footer') in page
    assert 'href="frontend/shared/site.css"' in page
    assert 'src="frontend/shared/site.js"' in page
assert 'data:image' not in index
assert 'RICHON Estate Study Group 대표' not in index
assert 'alt="리치온 초이 강사"' not in index
assert '대표 멘토' in index and '리치온 아카데미 대표 멘토' in index and '실전 멘토' in index
assert '각 분야의 실전 관점은 강의별 커리큘럼 안에서 연결합니다.' not in index
assert '대중과 반대로 가는 길에서 기회를 찾아온 실전 투자자.' in index
for mentor in ('가위남','이루민','인생곰부','재부스','키네스트','후니동산'):
    assert f'<b>{mentor}</b>' in index
assert index.count('class="mentor-card"') == 6
assert index.count('class="mentor-field"') == 6
assert index.count('<div class="mentor-card">') == 6
assert index.count('id="burger"') == 1
assert index.count('class="site-footer"') == 1

assert len(apply) > 5000
assert apply.count('id="burger"') == 1
assert apply.count('class="site-footer"') == 1
assert "briefing:" not in apply and "welcome:" not in apply
for course in ("pre","study","redev","interior","subscription"):
    assert course+":{" in apply
assert "redev:{name:'재개발 중급반'" in apply and "status:'waitlist'" in apply
assert "interior:{name:'리치온 인테리어'" in apply and "status:'upcoming'" in apply
assert "subscription:{name:'청약 실전반'" in apply and "status:'upcoming'" in apply
assert 'class="course-cta a-wait" href="apply.html?course=redev">대기 신청 →' in index
assert '<span class="status waitlist">대기 신청</span>' in index
assert index.count('class="course-cta a-apply"') == 2
assert index.count('class="course-cta a-disabled" aria-disabled="true">모집 예정</span>') == 2
assert 'href="apply.html?course=interior"' not in index
assert 'href="apply.html?course=welcome"' not in index
assert index.count('aria-disabled="true">모집 예정</span>') == 2
assert "{{구글폼URL}}" in apply and "{{결제링크URL}}" in apply and "{{입금계좌}}" in apply
assert "현재는 UI 준비 상태입니다." in apply
assert 'apply.html은 fork/original 모두 현재 0 byte' not in work
assert '회원/로그인 공통 UI 마감 브랜치: `fix/member-shared-ui-closeout`' not in work
assert '원본 marururu00/richon-academy 반영 전에는 실제 공개 홈페이지 완료로 간주하지 않음' in work

images=[
    'seoul-redevelopment-study.jpg','pre-richon-course.jpg','richon-study-course.jpg',
    'redevelopment-reconstruction-course.jpg','space-design-course.jpg','subscription-course.jpg',
]
for name in images:
    path=ROOT/'assets'/'images'/name
    assert path.is_file() and path.stat().st_size > 1000
    assert ('assets/images/'+name) in index

css=(shared/'site.css').read_text()
js=(shared/'site.js').read_text()
assert '.site-footer-links a{color:inherit;' in css
assert 'html.site-menu-open{overflow:hidden}' in css
assert "document.documentElement.classList.toggle('site-menu-open', open)" in js

hero=(ROOT/'assets'/'hero'/'home-hero.css').read_text()
assert 'frontend/shared/site.css' in hero
assert '기존 리치온 헤더를 오프닝 뒤에만 노출' not in hero
assert '.hero-js .site-nav' in hero

print('PASS: public landing uses shared chrome, external images, unified course CTAs and approved mentor layout')


guide=(ROOT/'signup-guide.html').read_text()
footer=(shared/'footer.html').read_text()
privacy=(ROOT/'privacy.html').read_text()
terms=(ROOT/'terms.html').read_text()

assert 'href="/signup-guide.html"' in footer
for value in ('회원가입 전체 절차','이름','휴대전화번호','이메일','연령대','성별',
              'CI(연계정보)','중복가입 방지'):
    assert value in guide
assert '필수' in guide and '선택' in guide
assert 'CI(연계정보)' in privacy and '중복 회원가입 방지' in privacy
assert '원문 CI는 저장하지 않고 단방향 변환값' in privacy
assert '비밀번호, 이름, 닉네임, 생년월일' not in privacy
assert '본인확인값(CI,DI)' not in privacy
assert '중복 회원가입 방지 및 기존 회원 비교 식별' in terms
