"""Move the approved v7 hero only; preserve production content below it."""
import base64, hashlib, re
from pathlib import Path

ROOT=Path.cwd()
def build(root=ROOT):
    index=(root/'index.html').read_text()
    preview=(root/'index-test.html').read_text()
    def gitblob(data):
        b=data if isinstance(data,bytes) else data.encode()
        return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    assert gitblob(index)=='251a6f099a51c893950a81d2cda917dbde6b4166'
    assert gitblob(preview)=='b24ad4cb1b573b51264bc74f1665b690e30c7c13'
    css=re.findall(r'<style(?:\s[^>]*)?>(.*?)</style>',preview,re.S)[1]
    a=css.index('    * { box-sizing: border-box; }')
    b=css.index('    .hero-scroll {',a)
    css=css[:a]+css[b:]
    css=css.replace('--ink: #191919;', '--hero-ink: #191919;').replace('var(--ink)', 'var(--hero-ink)')
    a=css.index('    /* 끝부분이 본문의 흰 화면과 자연스럽게 이어지는지 확인 */')
    b=css.index('    @media (max-width: 900px)',a)
    css=css[:a]+css[b:]
    a=css.index('    /* 운영 index 본문을 시각 확인용 정적 더미로 이어붙인다. */')
    b=css.index('    @media (prefers-reduced-motion: reduce)',a)
    css=css[:a]+css[b:]
    css=css.replace('.js ', '.hero-js ')
    m=re.search(r'data:image/webp;base64,([A-Za-z0-9+/=]+)',css)
    image=base64.b64decode(m[1],validate=True)
    css=css[:m.start()]+ 'richon-hero-desktop.webp'+css[m.end():]
    css=css.replace('assets/hero/richon-hero-mobile.webp','richon-hero-mobile.webp')
    marker='      opacity: 0;\n      visibility: hidden;\n      transform: translateY(-16px);\n      pointer-events: none;'
    assert css.count(marker)==1
    css=css.replace(marker, '      opacity: 1;\n      visibility: visible;\n      transform: none;\n      pointer-events: auto;')
    css+='''\n/* Production-only integration: no preview interaction disabling. */
.hero-js .site-nav {opacity:0;visibility:hidden;transform:translateY(-16px);pointer-events:none}
html:not(.hero-js) .hero-scroll {height:100svh;min-height:620px}
html:not(.hero-js) .hero-dim {display:none}
html:not(.hero-js) .reveal {opacity:1;transform:none}
#top {display:block;height:0}
#proof,#programs,#instructor {scroll-margin-top:90px}
@media(max-width:900px){.site-menu {height:100dvh;padding:100px 24px 32px;justify-content:flex-start}}
@media(prefers-reduced-motion:reduce){.hero-js .site-nav {opacity:1;visibility:visible;transform:none;pointer-events:auto}}
'''
    nav=re.search(r'  <span id="top".*?</nav>',preview,re.S)[0]
    nav=nav.replace('id="siteMenu"','id="navMenu"').replace('id="siteBurger"','id="burger"')
    nav=nav.replace('aria-label="메뉴"','type="button" aria-controls="navMenu" aria-label="메뉴"')
    hero=re.search(r'    <section class="hero-scroll".*?</section>',preview,re.S)[0]
    script=re.findall(r'<script[^>]*>(.*?)</script>',preview,re.S)[-1]
    script=script.replace("const siteBurger = document.getElementById('siteBurger');",'')
    script=script.replace("const siteMenu = document.getElementById('siteMenu');",'')
    a=script.index("      siteBurger?.addEventListener('click'")
    b=script.index("      window.addEventListener('scroll'",a)
    script=script[:a]+script[b:]
    script=script.replace("      let ticking = false;", "      document.documentElement.classList.add('hero-js');\n      let ticking = false;")
    script=script.replace('scrollSection.offsetHeight - window.innerHeight', "scrollSection.offsetHeight - document.getElementById('heroSticky').offsetHeight")
    index,n=re.subn(r'<nav>.*?</nav>\s*<header class="hero blueprint" id="top">.*?</header>',nav+'\n\n'+hero,index,count=1,flags=re.S)
    assert n==1
    index=index.replace('</head>', '<link rel="preload" as="image" href="assets/hero/richon-hero-mobile.webp" type="image/webp" media="(max-width:768px)">\n<link rel="stylesheet" href="assets/hero/home-hero.css">\n<script defer src="assets/hero/home-hero.js"></script>\n</head>')
    index=index.replace('▸ 이미지는 파일 안에 포함되어 있어 따로 둘 필요 없이 어디서든 표시됩니다.', '▸ 히어로는 assets/hero의 CSS·JS·WebP를 사용하며, 본문 이미지는 파일 안에 포함되어 있습니다.')
    index=index.replace('▸ 배포: index.html + apply.html 두 파일을 같은 폴더(저장소 최상단)에 두세요.', '▸ 배포: index.html + apply.html과 assets/hero 폴더를 함께 유지하세요.')
    index=index.replace("burger.classList.toggle('open');menu.classList.toggle('show')", "const open=burger.classList.toggle('open');menu.classList.toggle('show',open);burger.setAttribute('aria-expanded',String(open))")
    index=index.replace("burger.classList.remove('open');menu.classList.remove('show')", "burger.classList.remove('open');menu.classList.remove('show');burger.setAttribute('aria-expanded','false')")
    before=(root/'index.html').read_text()
    start='<section class="block light" id="proof">'
    assert before[before.index(start):before.index('<script>',before.index(start))]==index[index.index(start):index.index('<script>',index.index(start))]
    assert 'preview-content' not in index and 'preview-content' not in css
    assert 'pointer-events: none !important' not in css
    files={'index.html':index.encode(),'assets/hero/home-hero.css':css.encode(),'assets/hero/home-hero.js':script.encode(),'assets/hero/richon-hero-desktop.webp':image}
    for name,data in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return {name:gitblob(data) for name,data in files.items()}
if __name__=='__main__':
    import json
    print(json.dumps(build(),indent=2))
