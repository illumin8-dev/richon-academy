"""Static public UI contract checks; no network, credentials, or deployment."""
from pathlib import Path
import shared_chrome as chrome

ROOT=Path(__file__).resolve().parents[1]
index=(ROOT/'index.html').read_text()
apply=(ROOT/'apply.html').read_text()
guide=(ROOT/'signup-guide.html').read_text()
privacy=(ROOT/'privacy.html').read_text()
terms=(ROOT/'terms.html').read_text()
policy_css=(ROOT/'assets'/'pages'/'policy.css').read_text()
apply_css=(ROOT/'assets'/'pages'/'apply.css').read_text()
shared=ROOT/'frontend'/'shared'

footer=chrome.footer()
assert chrome.wrapped('header',chrome.render_header('landing')) in index
assert chrome.wrapped('header',chrome.render_header('portal')) in apply
for page in (index,apply):
    assert chrome.wrapped('footer',footer) in page
    assert 'href="frontend/shared/site.css"' in page
    assert 'src="frontend/shared/site.js"' in page
    assert 'src="frontend/shared/login.js"' in page
    assert 'data-account-entry="enabled"' not in page
    assert 'id="site-account-login"' in page and 'data-richon-login hidden' in page
    assert 'id="site-account-me"' in page
for landing_only in ('/#proof','/#programs','/#instructor'):
    assert landing_only in index
    assert landing_only not in apply
assert 'id="navMenu"' not in apply
assert '<link rel="stylesheet" href="/assets/pages/apply.css">' in apply
assert '<style>' not in apply
assert '.apply-grid' in apply_css and '.apply-summary' in apply_css and '.apply-curriculum' in apply_css
assert 'id="burger"' not in apply
assert 'data:image' not in index
assert 'RICHON Estate Study Group 대표' not in index
assert 'alt="리치온 초이 강사"' not in index
assert 'RICHON MENTORS' in index and '리치온 멘토진' in index
assert '대표 멘토 1명과 분야별 실전 멘토 6명이 함께합니다.' in index
assert '대표 멘토' in index and '리치온 아카데미 대표 멘토' in index and '실전 멘토' in index
assert index.count('class="mentor-feature-card"') == 1
assert 'class="mentor-kicker"' not in index
assert index.count('id="burger"') == 1
assert index.count('class="site-footer"') == 1
assert 'body{padding-bottom:74px}' not in index
assert 'id="calendar"' in index
assert 'id="landing-calendar"' in index
assert 'assets/calendar/public-calendar.css' in index
assert 'assets/calendar/public-calendar.js' in index
assert 'assets/calendar/calendar-logo.svg' in index
for relative in ('calendar-logo.svg','public-calendar.css','public-calendar.js'):
    path=ROOT/'assets'/'calendar'/relative
    assert path.is_file() and path.stat().st_size > 100
calendar_css=(ROOT/'assets'/'calendar'/'public-calendar.css').read_text()
assert '.landing-calendar-nav button:first-child{grid-column:1}' in calendar_css
assert '.landing-calendar-nav button:last-child{grid-column:3}' in calendar_css
assert 'grid-template-columns:46px 1fr 46px' in calendar_css
assert '.landing-calendar-nav button span{pointer-events:none' in calendar_css
assert 'max-width:980px' in calendar_css
assert 'min-height:88px' in calendar_css
assert '.landing-calendar-day{min-height:88px;padding:0 3px' in calendar_css
assert '.landing-calendar-event-content{display:block;margin:2px 0 0;color:#444;font-size:11.5px' in calendar_css
assert '@media(min-width:901px){.landing-calendar-event-content{white-space:nowrap}}' in calendar_css
assert 'id="landing-calendar-prev" type="button" aria-label="이전 달" hidden><span aria-hidden="true">←</span>' in index
assert 'id="landing-calendar-next" type="button" aria-label="다음 달" hidden><span aria-hidden="true">→</span>' in index
calendar_js=(ROOT/'assets'/'calendar'/'public-calendar.js').read_text()
assert "/portal/api/public/calendar?month=" in calendar_js
assert "credentials:'omit'" in calendar_js
for forbidden in ('innerHTML','insertAdjacentHTML','document.cookie','localStorage.','sessionStorage.','eval('):
    assert forbidden not in calendar_js
assert '.cal-' not in index
assert '캘린더 셀 살짝 반응' not in index

assert len(apply) > 5000
assert apply.count('id="burger"') == 0
assert apply.count('class="site-footer"') == 1
assert "briefing:" not in apply and "welcome:" not in apply
for course in ("pre","study","redev","interior","subscription"):
    assert course+":{" in apply
assert "redev:{name:'재개발 중급반'" in apply and "status:'waitlist'" in apply
assert "interior:{name:'리치온 인테리어'" in apply and "status:'upcoming'" in apply
assert "subscription:{name:'청약 실전반'" in apply and "status:'upcoming'" in apply
assert 'href="apply.html?course=redev">대기 신청 →' in index
assert index.count('href="apply.html?course=pre">신청하기 →') == 1
assert index.count('href="apply.html?course=study">신청하기 →') == 1
assert 'href="apply.html?course=interior">소개 →' in index
assert 'href="apply.html?course=subscription">소개 →' in index
assert 'href="apply.html?course=welcome"' not in index
assert index.count('aria-disabled="true">모집 예정</span>') == 2
assert index.count('class="pcard') >= 6
assert 'class="pcard coming-soon reveal"' in index
assert 'aria-label="새로운 과정 준비 중"' in index
assert 'COMING SOON' in index and '새로운 과정 준비 중' in index
assert '리치온의 다음 실전 과정을 준비하고 있습니다.' not in index
assert 'coming-soon-copy' not in index
assert '<h3 class="coming-soon-title">' not in index
assert 'placeholder-plus' not in index
assert '소개 ↗' not in index and '소식 보기 ↗' not in index
assert index.count('class="course-cta') >= 5
assert '투자원칙, 갭투자, 서울 초기재개발, 시장구조까지. 처음 시작하는 분이 시장을 읽는 기초 프레임을 세우는 과정.' in index
assert '정밀한 입지 분석과 인프라 변화 예측으로 수도권 주요 재개발/재건축 단지를 공략하는 심화 과정.' in index
assert '<p>대중과 반대로 가는 길에서 기회를 찾아온 실전 투자자.</p>' in index
assert '<p>부동산 동향 / 경매 / 재개발 / 인테리어를 아우르는 통합적 관점으로 시장의 불확실성을 기회로 바꾸는 인사이트를 전합니다.</p>' in index
assert '<p>강의에서는 시장 흐름을 먼저 읽고, 그 흐름에 맞는 투자 방식과 물건을 고르는 판단 기준을 중심으로 설명합니다.</p>' in index
assert index.count('class="mentor-card"') == 6 and index.count('class="mentor-field"') == 6
assert 'aria-label="리치온 실전 멘토 6명"' in index
assert "{{구글폼URL}}" in apply and "{{결제링크URL}}" in apply and "{{입금계좌}}" in apply
assert '신청 흐름' not in apply
assert 'class="apply-flow"' not in apply
assert 'class="apply-includes"' not in apply
assert '현재 모집 상태를 확인한 뒤 신청해 주세요.' not in apply
assert '과정별 일정과 운영 방식은 신청 안내에서 최종 확인합니다.' not in apply
assert '신청 정보와 결제 정보는 실제 운영 링크가 열린 뒤 입력합니다.' not in apply
assert '접수 확인 후 수강 방법과 준비사항을 별도로 안내합니다.' not in apply
assert '현재는 UI 준비 상태입니다.' not in apply
# PR #59에서 보존된 과정별 상세 소개 이미지 49장을 현재 신청 UI에 복원한다.
for value in (
    'id="course-visual"', 'id="course-gallery"',
    'assets/images/pre-richon-course.jpg', 'assets/images/richon-study-course.jpg',
    'assets/images/redevelopment-reconstruction-course.jpg', 'assets/images/space-design-course.jpg',
    'assets/images/subscription-course.jpg',
):
    assert value in apply
for prefix,count in (('pre',1),('study',12),('redevelopment',11),('interior',15),('subscription',10)):
    for number in range(1,count+1):
        path=ROOT/'assets'/'apply'/f'{prefix}-{number:02d}.jpg'
        assert path.is_file() and path.stat().st_size > 1000
        assert f'assets/apply/{prefix}-{number:02d}.jpg' in apply
assert apply.count('assets/apply/') == 57
for number in range(2,10):
    path=ROOT/'assets'/'apply'/f'pre-{number:02d}.png'
    assert path.is_file() and path.stat().st_size > 1000
    assert f'assets/apply/pre-{number:02d}.png' in apply
for value in (
    '2개월(8주) 과정', '매주 목요일 저녁 9시', '온라인 ZOOM 라이브',
    'Week 1','부동산 투자원칙','Week 2','갭투자','Week 3','서울초기재개발',
    'Week 4','부동산 기초 및 시장구조','Week 5','분양권 전략',
    'Week 6','지방 재개발','Week 7','경매 권리분석 및 수익화',
    'Week 8','현장 및 멘토와의 만남',
):
    assert value in apply
for copy in (
    '부동산 투자원칙·갭투자·서울 초기재개발·시장구조부터 분양권·지방 재개발·경매까지, 실전형 순환 학습으로 기초를 세우는 정규 과정.',
    '현금흐름, 갭투자, 서울 초기재개발, 경매 등 매주 실전 주제로 깊이 파고드는 핵심 스터디.',
    '정밀한 입지 분석과 인프라 변화 예측으로 수도권 주요 재개발/재건축 단지를 공략하는 심화 과정.',
    '자산 가치를 높이는 공간 디자인 전문 과정. 수익률로 이어지는 인테리어 전략과 공간가치 판단을 다룹니다.',
    '분양권과 청약 흐름을 시장/지역 분석과 연결해 보는 신규 과정입니다. 세부 커리큘럼 확정 후 오픈됩니다.',
):
    assert copy in apply

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
assert 'body.richon-page{box-sizing:border-box;padding-top:74px;min-height:100vh;min-height:100dvh;display:flex;flex-direction:column}' in css
assert '.site-footer{margin-top:auto;flex-shrink:0;' in css
for page in (apply,guide,privacy,terms):
    assert '<body class="richon-page' in page
assert '@import' not in css and 'pretendard@v1.3.9' not in css
font_link=chrome.font_link()
for page in (index,apply,guide,privacy,terms):
    assert page.count(font_link)==1
assert 'html.site-menu-open{overflow:hidden}' in css
assert "document.documentElement.classList.toggle('site-menu-open', open)" in js

hero=(ROOT/'assets'/'hero'/'home-hero.css').read_text()
assert 'frontend/shared/site.css' in hero
assert '기존 리치온 헤더를 오프닝 뒤에만 노출' not in hero
assert '.hero-js .site-nav' in hero

print('PASS: public landing uses shared chrome, external images and approved mentor layout')


assert 'href="/signup-guide.html"' not in footer
assert chrome.wrapped('header',chrome.render_header('portal')) in guide
assert chrome.wrapped('footer',footer) in guide
assert chrome.wrapped('header',chrome.render_header('document')) in privacy
assert chrome.wrapped('header',chrome.render_header('document')) in terms
assert chrome.wrapped('footer',footer) in privacy
assert chrome.wrapped('footer',footer) in terms
for page in (privacy,terms):
    assert '<link rel="stylesheet" href="/assets/pages/policy.css">' in page
    assert '<style>' not in page
assert '--maxw:860px' in policy_css and 'header.doc' in policy_css and 'h3.art' in policy_css
for landing_only in ('/#proof','/#programs','/#instructor'):
    assert landing_only not in guide
assert 'id="navMenu"' not in guide
assert 'id="burger"' not in guide
assert 'src="/frontend/shared/login.js"' in guide
for value in ('회원가입 전체 절차','이름','휴대전화번호','이메일','연령대','성별',
              'CI(연계정보)','중복가입 방지'):
    assert value in guide
assert '필수' in guide and '선택' in guide
assert 'CI(연계정보)' in privacy and '중복 회원가입 방지' in privacy
assert '원문 CI는 저장하지 않고 단방향 변환값' in privacy
assert '비밀번호, 이름, 닉네임, 생년월일' not in privacy
assert '본인확인값(CI,DI)' not in privacy
assert '중복 회원가입 방지 및 기존 회원 비교 식별' in terms

login_js=(shared/'login.js').read_text()
assert "dialog.showModal()" in login_js
assert "fetch('/auth/login?view=modal&return_to='" in login_js
assert "'불러오는 중입니다.'" in login_js
