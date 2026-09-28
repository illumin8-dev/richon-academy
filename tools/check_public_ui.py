"""Static public UI contract checks; no network, credentials, or deployment."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
index=(ROOT/'index.html').read_text()
apply=(ROOT/'apply.html').read_text()
shared=ROOT/'frontend'/'shared'

def wrapped(name):
    value=(shared/(name+'.html')).read_text().strip()
    return '<!-- richon:shared-'+name+' -->\n'+value+'\n<!-- /richon:shared-'+name+' -->'

for page in (index,apply):
    assert wrapped('header') in page
    assert wrapped('footer') in page
    assert 'href="frontend/shared/site.css"' in page
    assert 'src="frontend/shared/site.js"' in page
    assert 'data:image' not in page
assert 'class="richon-page apply-page"' in apply
assert 'RICHON Estate Study Group 대표' not in index
assert 'alt="리치온 초이 강사"' not in index
assert '대표 멘토' in index and '리치온 아카데미 대표 멘토' in index and '실전 멘토' in index
assert index.count('id="burger"') == 1
assert index.count('class="site-footer"') == 1

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

slides=list((ROOT/'assets'/'apply').glob('*.jpg'))
assert len(slides)==49
assert all(path.stat().st_size>1000 for path in slides)
for path in slides:
    assert ('assets/apply/'+path.name) in apply
for placeholder in ('{{구글폼URL}}','{{결제링크URL}}','{{입금계좌}}'):
    assert placeholder in apply
assert 'loading="lazy" decoding="async"' in apply

hero=(ROOT/'assets'/'hero'/'home-hero.css').read_text()
assert 'frontend/shared/site.css' in hero
assert '기존 리치온 헤더를 오프닝 뒤에만 노출' not in hero
assert '.hero-js .site-nav' in hero

print('PASS: public landing/apply use shared chrome, external images and approved mentor layout')
