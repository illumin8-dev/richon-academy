"""Real Chromium navigation to a local synthetic host. No production traffic."""
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
import json,mimetypes,os,subprocess
ROOT=Path.cwd();OUT=Path(os.environ.get('HERO_REPORT_DIR','/tmp/hero-report'));OUT.mkdir(parents=True,exist_ok=True)
ORIGIN='https://richon.test'

def main():
    before=subprocess.check_output(['git','show','03f4da08cefa15ec4dfab882788fc52983c8d084:index.html']).decode()
    after=(ROOT/'index.html').read_text();start='<section class="block light" id="proof">'
    assert before[before.index(start):before.index('<script>',before.index(start))]==after[after.index(start):after.index('<script>',after.index(start))]
    assert before[before.index('<div class="ctabar">'):]==after[after.index('<div class="ctabar">'):]
    assert 'preview-content' not in after
    results=[]
    with sync_playwright() as p:
        args={'headless':True}
        if os.getenv('CHROMIUM_EXECUTABLE'):args['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
        browser=p.chromium.launch(**args)
        try:
            cases=[(320,640,True,'no-preference'),(390,844,True,'no-preference'),(768,1024,True,'no-preference'),(900,700,True,'no-preference'),(1440,900,True,'no-preference'),(390,844,True,'reduce'),(1440,900,False,'no-preference')]
            for width,height,js,motion in cases:
                context=browser.new_context(viewport={'width':width,'height':height},java_script_enabled=js,reduced_motion=motion,service_workers='block')
                seen=[];errors=[]
                def respond(route):
                    u=urlsplit(route.request.url)
                    if u.netloc!='richon.test':
                        route.fulfill(status=200,body='',content_type='text/css');return
                    assert route.request.method=='GET'
                    path='index.html' if u.path=='/' else u.path.lstrip('/')
                    if path=='apply.html':route.fulfill(body='<h1>Application route test</h1>',content_type='text/html');return
                    f=ROOT/path
                    if path not in {'index.html','assets/hero/home-hero.css','assets/hero/home-hero.js','assets/hero/richon-hero-desktop.webp','assets/hero/richon-hero-mobile.webp'}:
                        route.fulfill(status=404,body='not found');return
                    assert f.is_file();seen.append(path)
                    route.fulfill(body=f.read_bytes(),content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
                context.route('**/*',respond)
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(ORIGIN+'/',wait_until='networkidle')
                if js:
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert page.locator('#heroLight').count()==1
                assert 'assets/hero/richon-hero-mobile.webp' in seen if width<=768 else 'assets/hero/richon-hero-desktop.webp' in seen
                if js and motion!='reduce':
                    assert page.locator('#siteNav').evaluate('(e)=>getComputedStyle(e).visibility')=='hidden'
                    page.screenshot(path=str(OUT/f'{width}-off.png'))
                    page.evaluate("window.scrollTo({top:document.querySelector('#heroScroll').offsetHeight-document.querySelector('#heroSticky').offsetHeight,behavior:'instant'})")
                    page.wait_for_timeout(120)
                    assert page.locator('#siteNav').evaluate('(e)=>getComputedStyle(e).visibility')=='visible'
                    assert float(page.locator('#heroLight').evaluate('(e)=>getComputedStyle(e).opacity'))>.99
                    assert float(page.locator('#copyOn').evaluate('(e)=>getComputedStyle(e).opacity'))>.99
                assert page.locator('#siteNav .site-btn-o').is_visible()
                page.screenshot(path=str(OUT/f'{width}-{js}-{motion}-on.png'))
                if js and width<=900:
                    page.locator('#burger').click()
                    assert page.locator('#burger').get_attribute('aria-expanded')=='true'
                    page.locator('#navMenu a[href="#programs"]').click()
                    page.wait_for_timeout(100)
                    assert page.url.endswith('#programs')
                    assert page.locator('#burger').get_attribute('aria-expanded')=='false'
                assert page.locator('#programs a[href^="apply.html"]').count()>0
                assert page.locator('footer a[href="privacy.html"]').count()==1
                assert page.locator('#siteNav a[href="https://open.kakao.com/o/gPdQcklh"]').count()==1
                page.locator('#siteNav .site-btn-o').click()
                assert urlsplit(page.url).path=='/apply.html'
                assert not errors,errors
                results.append({'width':width,'height':height,'javascript':js,'motion':motion,'result':'passed'})
                print('PASS',results[-1]);context.close()
        finally:browser.close()
    (OUT/'results.json').write_text(json.dumps({'cases':results,'lower_content':'byte-identical','production_network':'none'},indent=2))
    print('PASS: 7 browser cases and preserved production lower-content/footer/CTA')
if __name__=='__main__':main()
