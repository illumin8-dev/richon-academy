"""Rendered provider geometry only; all requests fulfilled by synthetic app."""
from pathlib import Path
import os
import sys
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from test_oauth import app, ORIGIN


def main():
    with TestClient(app(), base_url=ORIGIN) as client, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for width in (320, 390, 1280):
                context = browser.new_context(viewport={'width': width, 'height': 900}, service_workers='block')
                failures = []
                def fulfill(route):
                    request = route.request; url = urlsplit(request.url)
                    if (url.scheme + '://' + url.netloc != ORIGIN or request.method != 'GET'
                            or url.path not in {'/auth/login', '/auth/assets/kakao-login.png', '/auth/assets/naver-login.png'}):
                        failures.append('unexpected-network'); route.abort(); return
                    response = client.get(url.path, follow_redirects=False)
                    route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
                context.route('**/*', fulfill)
                page = context.new_page(); page.goto(ORIGIN + '/auth/login', wait_until='networkidle')
                assert not failures
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                boxes = []
                for name, image_width, image_height, marks in (
                    ('kakao', 448, 46, (173, 275)), ('naver', 368, 48, (124, 244))):
                    button = page.locator('.' + name + '-login'); image = button.locator('img')
                    assert image.evaluate('(e)=>e.complete && e.naturalWidth>0')
                    b = button.bounding_box(); i = image.bounding_box(); boxes.append(b)
                    assert b['height'] == 48 and b['width'] >= 224
                    assert i['width'] == image_width and i['height'] == image_height
                    assert abs((i['x'] + i['width']/2) - (b['x'] + b['width']/2)) <= 0.5
                    assert i['x'] + marks[0] >= b['x'] + 12
                    assert i['x'] + marks[1] <= b['x'] + b['width'] - 12
                    button.focus()
                    assert button.evaluate('(e)=>getComputedStyle(e).outlineStyle') != 'none'
                assert boxes[0]['width'] == boxes[1]['width']
                assert boxes[1]['y'] >= boxes[0]['y'] + boxes[0]['height']
                if os.getenv('PROVIDER_DESIGN_SCREENSHOTS'):
                    out = Path(os.environ['PROVIDER_DESIGN_SCREENSHOTS']); out.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(out / f'providers-{width}.png'), full_page=True)
                print(f'PASS: official provider images / {width}px / equal 48px buttons / legible fixed symbols')
                context.close()
        finally:
            browser.close()
    print('3 rendering scenarios passed; no provider login, live site, or database used.')


if __name__ == '__main__':
    main()
