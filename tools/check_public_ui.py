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
assert "{{구글폼URL}}" in apply and "{{결제링크URL}}" in apply and "{{입금계좌}}" in apply
assert '신청 흐름' not in apply
assert 'class="apply-flow"' not in apply
assert 'class="apply-includes"' not in apply
assert '현재 모집 상태를 확인한 뒤 신청해 주세요.' not in apply
assert '과정별 일정과 운영 방식은 신청 안내에서 최종 확인합니다.' not in apply
assert '신청 정보와 결제 정보는 실제 운영 링크가 열린 뒤 입력합니다.' not in apply
assert '접수 확인 후 수강 방법과 준비사항을 별도로 안내합니다.' not in apply
assert '현재는 UI 준비 상태입니다.' not in apply
for copy in (
    '투자원칙, 갭투자, 서울 초기재개발, 시장구조까지. 처음 시작하는 분이 시장을 읽는 기초 프레임을 세우는 과정.',
    '현금흐름, 갭투자, 서울 초기재개발, 경매 등 매주 실전 주제로 깊이 파고드는 핵심 스터디.',
    '정밀한 입지 분석과 인프라 변화 예측으로 수도권 주요 재개발/재건축 단지를 공략하는 심화 과정.',
    '자산 가치를 높이는 공간 디자인 전문 과정. 수익률로 이어지는 인테리어 전략과 공간가치 판단을 다룹니다.',
    '분양권과 청약 흐름을 시장/지역 분석과 연결해 보는 신규 과정입니다. 세부 커리큘럼 확정 후 오픈됩니다.',
):
    assert copy in apply
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

print('PASS: public landing uses shared chrome, external images and approved mentor layout')


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
