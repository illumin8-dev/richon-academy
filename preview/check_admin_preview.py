"""Synthetic UI test only. No OAuth, database or real customer data."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--set-content',action='store_true');parser.add_argument('--executable');parser.add_argument('--screenshots');args=parser.parse_args()
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**({'executable_path':args.executable} if args.executable else {}))
    page=browser.new_page(viewport={'width':1440,'height':980})
    errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
    if args.set_content:page.set_content((ROOT/'admin-test.html').read_text())
    else:page.goto((ROOT/'admin-test.html').as_uri())
    expect(page.locator('#rows tr')).to_have_count(4)
    def settled():expect(page.locator('#save')).to_be_enabled()
    def search(q='',archived='false'):
        page.locator('#q').fill(q);page.locator('#archive-filter').select_option(archived)
        page.locator('#filters button[type=submit]').click();page.wait_for_timeout(250)
    page.locator('#new').click()
    f=page.locator('#edit-form');f.locator('[name=name]').fill('[가상] 신규 테스트')
    f.locator('[name=nickname]').fill('첫번째별명');f.locator('[name=email]').fill('new@example.invalid')
    f.locator('[name=phone]').fill('010-0000-1111');f.locator('[name=original_joined_on]').fill('2026-07-01')
    f.locator('[name=months]').select_option('3');f.locator('[name=confirmed]').check()
    f.locator('[name=quoted_amount_krw]').fill('210000');f.locator('[name=reason]').fill('가상 이전 명단 확인')
    f.locator('[type=submit]').click();expect(page.locator('#editor')).not_to_be_visible();settled()
    search('신규 테스트');expect(page.locator('#rows tr')).to_have_count(1)
    expect(page.locator('#rows')).to_contain_text('2026-12')
    def open_detail():
        settled();page.locator('#rows .name-button').first.click();expect(page.locator('#detail')).to_be_visible()
    open_detail();expect(page.locator('#profile-detail')).to_contain_text('new@example.invalid')
    page.locator('#edit-profile').click();f.locator('[name=nickname]').fill('<img src=x onerror=alert(1)>')
    f.locator('[name=reason]').fill('가상 닉네임 변경');f.locator('[type=submit]').click();expect(page.locator('#editor')).not_to_be_visible();settled()
    expect(page.locator('#rows')).to_contain_text('<img src=x onerror=alert(1)>');assert page.locator('#rows img').count()==0
    open_detail();page.locator('#extend').click();t=page.locator('#term-form')
    t.locator('[name=months]').select_option('1');t.locator('[name=confirmed]').check();t.locator('[name=reason]').fill('가상 한 달 연장')
    t.locator('[type=submit]').click();expect(page.locator('#term-editor')).not_to_be_visible();settled();expect(page.locator('#rows')).to_contain_text('2027-01')
    open_detail();page.locator('#extend').click();t.locator('[name=months]').select_option('12');t.locator('[name=reason]').fill('가상 미확정 연장');t.locator('[type=submit]').click();expect(page.locator('#term-editor')).not_to_be_visible();settled();expect(page.locator('#rows')).to_contain_text('2027-01');expect(page.locator('#rows')).to_contain_text('1건 대기')
    open_detail();expect(page.locator('#extend')).to_be_disabled();page.get_by_role('button',name='미확정 신청 수정').click();t.locator('[name=months]').select_option('3');t.locator('[name=confirmed]').check();t.locator('[name=reason]').fill('가상 연장 내역 확정');t.locator('[type=submit]').click();expect(page.locator('#term-editor')).not_to_be_visible();settled();expect(page.locator('#rows')).to_contain_text('2027-04')
    open_detail();page.locator('#other-course').click();f.locator('[name=course_id]').select_option('manual-demo-free');expect(f.locator('[name=months]')).to_have_value('2');expect(f.locator('[name=name]')).to_be_disabled();f.locator('[name=confirmed]').check();f.locator('[name=reason]').fill('가상 두 번째 과정');f.locator('[type=submit]').click();expect(page.locator('#editor')).not_to_be_visible();settled();expect(page.locator('#rows tr')).to_have_count(2)
    open_detail();page.locator('#archive').click();page.locator('#archive-form [name=reason]').fill('가상 보관 테스트');page.locator('#archive-save').click();expect(page.locator('#archive-editor')).not_to_be_visible();settled();expect(page.locator('#rows tr')).to_have_count(1)
    search('신규 테스트','true');expect(page.locator('#rows tr')).to_have_count(1);open_detail();page.locator('#archive').click();page.locator('#archive-form [name=reason]').fill('가상 복원 테스트');page.locator('#archive-save').click();expect(page.locator('#archive-editor')).not_to_be_visible();settled();expect(page.locator('#rows tr')).to_have_count(0)
    search('신규 테스트');expect(page.locator('#rows tr')).to_have_count(2)
    page.locator('#new-course').click();cf=page.locator('#course-form');cf.locator('[name=title]').fill('[가상] 신규 과정');cf.locator('[name=start_month]').fill('2026-11');cf.locator('[name=price_krw]').fill('1000');cf.locator('[name=reason]').fill('가상 기록용 과정');cf.locator('[type=submit]').click();expect(page.locator('#course-editor')).not_to_be_visible();settled();expect(page.locator('#course-filter')).to_contain_text('[가상] 신규 과정')
    search();expect(page.locator('#rows tr')).to_have_count(6)
    for width in (320,390,768,1440):
        page.set_viewport_size({'width':width,'height':980});page.wait_for_timeout(80)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),width
    if args.screenshots:
        dst=Path(args.screenshots);dst.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(dst/'admin-test-desktop.png'),full_page=True)
        page.locator('#new').click();page.screenshot(path=str(dst/'manual-registration.png'),full_page=True);page.locator('[data-close=editor]').first.click()
        page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(dst/'admin-test-mobile.png'),full_page=True)
    page.locator('#logout').click();expect(page.locator('#content')).not_to_be_visible();expect(page.locator('#rows tr')).to_have_count(0)
    assert not errors,errors
    assert not [url for url in requests if not url.startswith('file:')],requests
    browser.close()
print('PASS: synthetic UI create/read/profile edit/pending edit/extension/archive/restore/course add/shared learner/XSS/month display/320-1440px/logout. No real backend called.')
