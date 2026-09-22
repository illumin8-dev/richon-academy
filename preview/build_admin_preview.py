"""Generate a public, network-free demo from the same production UI. No secrets."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'backend'/'portal_static'
html=(STATIC/'manual.html').read_text()
js=(STATIC/'manual.js').read_text().replace('crypto.randomUUID()', 'demoUUID()')
start=js.index('// Real transport.')
end=js.index('// END REAL TRANSPORT')+len('// END REAL TRANSPORT')
js=js[:start]+(ROOT/'preview'/'manual-demo.js').read_text()+js[end:]
html=html.replace('<link rel="stylesheet" href="/portal/manual-assets/manual.css">','<style>'+(STATIC/'manual.css').read_text()+'</style>')
html=html.replace('<script defer src="/portal/manual-assets/manual.js"></script>','')
html=html.replace('<head>','<head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; connect-src \'none\'; base-uri \'none\'; form-action \'none\'">')
html=html.replace('<body>','<body><div class="demo-ribbon"><strong>샘플 데이터 미리보기 — 실제 개인정보를 입력하지 마세요.</strong> 모든 변경은 이 탭의 메모리에만 남으며 새로고침하면 초기화됩니다.</div>')
# This demo is one standalone page. Hide links to unavailable private routes.
html=html.replace('<a href="/portal/enrollments">월별 통합 수강관리</a>','<a href="#filters">수강월 / 과정별 조회</a>')
html=html.replace('<a href="/portal/manual" aria-current="page">','<a href="#main" aria-current="page">')
html=html.replace('<a href="/portal/admin">회원 / 강의 / 주문</a>','<a href="#new">수동 등록 / 수정</a>')
html=html.replace('<a href="/portal/mypage">마이페이지 ↗</a>','')
html=html.replace('href="https://richonacademy.com/"','href="#main"')
html=html.replace('</body>','<script>'+js+'</script></body>')
assert 'fetch(' not in html and 'localStorage' not in html and 'sessionStorage' not in html
(ROOT/'admin-test.html').write_text(html)
print('Generated admin-test.html: in-memory CRUD, no network transport or credentials')
