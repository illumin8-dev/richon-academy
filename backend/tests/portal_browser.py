"""Isolated UI checks with intercepted synthetic API responses, never real login.

No fixture data or mock-login endpoint is installed in the production app.
Run: python backend/tests/portal_browser.py [screenshot-directory]
"""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit, parse_qs
import sys

from playwright.sync_api import sync_playwright, expect

STATIC = Path(__file__).resolve().parents[1] / 'portal_static'
TIMESTAMP='2026-09-22T03:00:00Z'
PROFILE={'member_id':'00000000-0000-4000-8000-000000000001','display_name':'샘플 수강생','role':'member','created_at':TIMESTAMP,'providers':['kakao'],'linked_order_count':2}
SUMMARY={'members_total':12,'members_active':11,'courses_total':3,'courses_enabled':2,'orders_total':8,'pending_orders':8,'unlinked_orders':2}
ORDERS=[{'order_id':'ord_sample_0001','course_id':'sample-flow','course_title':'[샘플] 흐름을 읽는 부동산 투자법','cohort':'테스트 기수','amount_krw':1000,'currency':'KRW','status':'pending_payment','created_at':TIMESTAMP,'customer_name':'샘플 수강생','phone_masked':'010-****-0000','email_masked':'s***@example.invalid','member_linked':True},
{'order_id':'ord_sample_0002','course_id':'sample-basic','course_title':'[샘플] 프리리치온 기초 과정','cohort':'테스트 기수','amount_krw':1000,'currency':'KRW','status':'pending_payment','created_at':TIMESTAMP,'customer_name':'샘플 신청자','phone_masked':'010-****-0000','email_masked':'t***@example.invalid','member_linked':False}]
MEMBERS=[{**PROFILE,'status':'active'}, {**PROFILE,'member_id':'00000000-0000-4000-8000-000000000002','display_name':'샘플 회원','providers':['naver'],'linked_order_count':0,'status':'active'}]
COURSES=[{'course_id':x['course_id'],'title':x['course_title'],'cohort':x['cohort'],'price_krw':1000,'enabled':True,'created_at':TIMESTAMP} for x in ORDERS]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name={'/portal/mypage':'mypage.html','/portal/admin':'admin.html','/portal/assets/portal.css':'portal.css','/portal/assets/portal.js':'portal.js'}.get(urlsplit(self.path).path)
        if not name: self.send_error(404);return
        content=(STATIC/name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.rsplit('.',1)[1]])
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
    def log_message(self,*args): pass


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    output=Path(sys.argv[1]) if len(sys.argv)>1 else None
    if output: output.mkdir(parents=True,exist_ok=True)
    scenario={'role':'member','fail_me':None,'fail_list':False,'xss':False,'more':False,'registration':None,'hold_me':False,'withdrawal_enabled':False,'fail_withdraw':None,'hold_withdraw':False,'hold_csrf':False}
    calls=[]
    held=[]
    held_withdraw=[]
    held_csrf=[]
    try:
        with sync_playwright() as p:
            kwargs={'headless':True}
            if os.environ.get('RICHON_BROWSER_EXECUTABLE'): kwargs['executable_path']=os.environ['RICHON_BROWSER_EXECUTABLE']
            browser=p.chromium.launch(**kwargs)
            context=browser.new_context(viewport={'width':1440,'height':1100},locale='ko-KR')
            def route(request):
                parsed=urlsplit(request.request.url)
                if parsed.netloc!=urlsplit(origin).netloc:
                    raise AssertionError('Unexpected external browser request')
                path=parsed.path
                if not (path.startswith('/portal/api/') or path.startswith('/auth/')):
                    return request.continue_()
                calls.append((path,request.request.method,parsed.query))
                code=200
                if path=='/portal/api/me':
                    data={**PROFILE,'role':scenario['role'],'display_name':'<img src=x onerror=alert(1)>' if scenario['xss'] else PROFILE['display_name']}
                    if scenario['registration'] is not None: data['registration']=scenario['registration']
                    if scenario['withdrawal_enabled']: data['consultation_withdrawal_available']=True
                    if scenario['hold_me']: held.append((request,data));return
                    if scenario['fail_me']: code=scenario['fail_me'];data={'detail':'test_only'}
                elif path=='/portal/api/admin/summary':data=SUMMARY
                elif path in ['/portal/api/me/orders','/portal/api/admin/orders','/portal/api/admin/members','/portal/api/admin/courses']:
                    data_rows=MEMBERS if path.endswith('/members') else COURSES if path.endswith('/courses') else ORDERS
                    q=parse_qs(parsed.query);offset=int(q.get('offset',['0'])[0])
                    rows=[] if q.get('q')==['검색결과없음'] else data_rows
                    data={'items':rows,'limit':20,'offset':offset,'has_more':scenario['more'] and offset==0}
                    if scenario['fail_list']:code=503;data={'detail':'test_only'}
                elif path=='/portal/api/me/consultation-consent/withdraw':
                    assert request.request.method=='POST'
                    assert request.request.post_data_json=={'confirm':True}
                    assert request.request.headers.get('x-csrf-token')=='test-only-not-session-token'
                    data={'consultation_consent':False,'age_range':None,'gender':None,'withdrawn_at':TIMESTAMP}
                    if scenario['fail_withdraw']:code=scenario['fail_withdraw'];data={'detail':'test_only'}
                    if scenario['hold_withdraw']:held_withdraw.append((request,data));return
                elif path=='/auth/csrf':
                    data={'csrf_token':'test-only-not-session-token'}
                    if scenario['hold_csrf']:held_csrf.append((request,data));return
                elif path=='/auth/logout':code=204;data=None
                else:raise AssertionError('Unexpected API path')
                request.fulfill(status=code,content_type='application/json',body='' if data is None else json.dumps(data))
            context.route('**/*',route)
            page=context.new_page()
            page.goto(origin+'/portal/mypage');expect(page.locator('.order-card')).to_have_count(2)
            expect(page.locator('#admin-link')).to_be_hidden()
            if output:page.screenshot(path=str(output/'mypage-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if output:page.screenshot(path=str(output/'mypage-mobile.png'),full_page=True)
            scenario['role']='admin';page.set_viewport_size({'width':1440,'height':1050})
            page.goto(origin+'/portal/admin');expect(page.locator('#table-body tr')).to_have_count(2)
            expect(page.locator('#members-total')).to_have_text('12')
            if output:page.screenshot(path=str(output/'admin-desktop.png'),full_page=True)
            for tab,title in [('members','회원 목록'),('courses','강의 목록'),('orders','신청·주문 내역')]:
                page.locator('[data-tab='+tab+']').click();expect(page.locator('#list-title')).to_have_text(title);expect(page.locator('#table-body tr')).to_have_count(2)
            page.locator('#search').fill('검색결과없음');page.locator('#search').press('Enter');expect(page.locator('#table-body')).to_contain_text('조건에 맞는 내역이 없습니다.')
            page.locator('#search').fill('');page.locator('#search').press('Enter');expect(page.locator('#table-body tr')).to_have_count(2)
            scenario['more']=True;page.locator('#refresh').click();expect(page.locator('#next')).to_be_enabled();page.locator('#next').click();expect(page.locator('#page-info')).to_contain_text('21–22');scenario['more']=False
            page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if output:page.screenshot(path=str(output/'admin-mobile.png'),full_page=True)
            scenario['fail_list']=True;page.locator('#refresh').click();expect(page.locator('#list-status')).to_contain_text('목록을 불러오지 못했습니다.');expect(page.locator('#table-body tr')).to_have_count(0)
            scenario['fail_list']=False;page.locator('#retry-list').click();expect(page.locator('#table-body tr')).to_have_count(2)
            scenario['role']='member';calls.clear();page.goto(origin+'/portal/admin');expect(page.locator('#gate-title')).to_have_text('관리자만 이용할 수 있습니다.')
            assert not any(path.startswith('/portal/api/admin/') for path,_,_ in calls)
            scenario['fail_me']=401;page.goto(origin+'/portal/mypage');expect(page.locator('#gate-title')).to_have_text('로그인이 필요합니다.');expect(page.locator('#content')).to_be_hidden()
            scenario['fail_me']=503;page.reload();expect(page.locator('#retry-gate')).to_be_visible()
            scenario['fail_me']=None;scenario['xss']=True;page.locator('#retry-gate').click();expect(page.locator('#welcome-name')).to_have_text('<img src=x onerror=alert(1)>');expect(page.locator('#welcome-name img')).to_have_count(0)
            page.locator('#logout').click();expect(page.locator('#gate-title')).to_have_text('로그아웃되었습니다.');expect(page.locator('.order-card')).to_have_count(0)
            assert any(path=='/auth/logout' and method=='POST' for path,method,_ in calls)
            # New policy data is only present on the authenticated own-profile
            # endpoint. Preserve the legacy mode until explicitly activated.
            fields=('phone','email','age','gender','consultation','consented')
            scenario.update(role='member',xss=False,fail_me=None)
            record={'name':'등록된 이름','phone':'01012345678','email':'profile@example.invalid',
                    'consultation_consent':True,'age_range':'30-39','gender':'female','consented_at':TIMESTAMP}
            for width in (320,390,1280):
                for consent in (False,True):
                    scenario['registration']={**record,'consultation_consent':consent}
                    page.set_viewport_size({'width':width,'height':950})
                    page.goto(origin+'/portal/mypage');expect(page.locator('.order-card')).to_have_count(2)
                    expect(page.locator('#profile-name-label')).to_have_text('이름')
                    expect(page.locator('#withdraw-consultation')).to_be_hidden()
                    expect(page.locator('#welcome-name')).to_have_text(record['name'])
                    expect(page.locator('#profile-phone')).to_have_text(record['phone'])
                    expect(page.locator('#profile-email')).to_have_text(record['email'])
                    expect(page.locator('#profile-age')).to_have_text('30~39세' if consent else '제공하지 않음')
                    expect(page.locator('#profile-gender')).to_have_text('여성' if consent else '제공하지 않음')
                    expect(page.locator('#profile-consultation')).to_have_text('동의' if consent else '동의하지 않음')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    page.locator('#logout').click();expect(page.locator('#gate-title')).to_have_text('로그아웃되었습니다.')
                    for field in fields:
                        expect(page.locator('#profile-'+field)).to_have_text('')
                        expect(page.locator('#profile-'+field+'-row')).to_be_hidden()
                    expect(page.locator('#avatar')).to_have_text('')
            # Missing/null optional fields (response_model excludes None) are
            # not fabricated. Unknown values must not display object properties.
            scenario['registration']={k:v for k,v in record.items() if k not in ('age_range','gender')}
            page.goto(origin+'/portal/mypage');expect(page.locator('#profile-age')).to_have_text('선택하지 않음')
            expect(page.locator('#profile-gender')).to_have_text('선택하지 않음')
            scenario['registration']={**record,'age_range':'toString','gender':'__proto__'}
            page.reload();expect(page.locator('#profile-age')).to_have_text('선택하지 않음')
            expect(page.locator('#profile-gender')).to_have_text('선택하지 않음')
            # Defensive rendering: even a bad server payload is text, not HTML.
            bad='<img src=x onerror=alert(1)>'
            scenario['registration']={**record,'name':bad,'email':bad}
            page.reload();expect(page.locator('#profile-email')).to_have_text(bad)
            expect(page.locator('#my-profile img')).to_have_count(0)
            expect(page.locator('#welcome-name img')).to_have_count(0)
            # Authentication loss clears previously rendered extra information.
            scenario['fail_me']=401
            page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
            expect(page.locator('#gate-title')).to_have_text('로그인이 필요합니다.')
            for field in fields: expect(page.locator('#profile-'+field)).to_have_text('')
            scenario.update(fail_me=None,registration=None)
            page.reload();expect(page.locator('.order-card')).to_have_count(2)
            expect(page.locator('#profile-name-label')).to_have_text('표시 이름')
            for field in fields: expect(page.locator('#profile-'+field+'-row')).to_be_hidden()
            # A delayed /me result must not restore personal data after pagehide.
            scenario.update(registration=record,hold_me=True)
            page.reload(wait_until='domcontentloaded')
            expect(page.locator('#gate-title')).to_have_text('로그인 상태를 확인하고 있습니다.')
            page.wait_for_function("performance.getEntriesByType('resource').some(e=>e.name.endsWith('/portal/assets/portal.js'))")
            for _ in range(50):
                if held: break
                page.wait_for_timeout(20)
            assert len(held)==1
            page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'))")
            waiting,payload=held.pop()
            waiting.fulfill(status=200,content_type='application/json',body=json.dumps(payload))
            page.wait_for_timeout(150)
            expect(page.locator('#content')).to_be_hidden()
            for field in fields: expect(page.locator('#profile-'+field)).to_have_text('')
            scenario['hold_me']=False
            # Optional withdrawal is opt-in; no mutation without confirmation.
            scenario.update(registration=record,withdrawal_enabled=True,hold_me=False)
            page.reload();expect(page.locator('.order-card')).to_have_count(2)
            expect(page.locator('#withdraw-consultation')).to_be_visible()
            calls.clear()
            page.once('dialog',lambda dialog:dialog.dismiss())
            page.locator('#withdraw-consultation').click()
            assert not any(path.endswith('/withdraw') for path,_,_ in calls)
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#withdraw-consultation').click()
            expect(page.locator('#profile-consultation')).to_have_text('동의 철회')
            expect(page.locator('#profile-age')).to_have_text('제공하지 않음')
            expect(page.locator('#profile-gender')).to_have_text('제공하지 않음')
            expect(page.locator('#profile-phone')).to_have_text(record['phone'])
            expect(page.locator('.order-card')).to_have_count(2)
            expect(page.locator('#withdraw-consultation')).to_be_hidden()
            assert sum(path.endswith('/withdraw') for path,_,_ in calls)==1
            # Failed writes are not displayed as erasure. CSRF is not admin denial.
            for code in (503,403,401):
                scenario['fail_withdraw']=code
                page.reload();expect(page.locator('#withdraw-consultation')).to_be_visible()
                page.once('dialog',lambda dialog:dialog.accept())
                page.locator('#withdraw-consultation').click()
                if code==401:
                    expect(page.locator('#gate-title')).to_have_text('로그인이 필요합니다.')
                    for field in fields: expect(page.locator('#profile-'+field)).to_have_text('')
                else:
                    expect(page.locator('#consultation-status')).to_contain_text('확인하지 못했습니다')
                    expect(page.locator('#profile-age')).to_have_text('30~39세')
                    expect(page.locator('#withdraw-consultation')).to_be_enabled()
                    expect(page.locator('#content')).to_be_visible()
            scenario.update(fail_withdraw=None,hold_withdraw=True)
            page.reload();expect(page.locator('#withdraw-consultation')).to_be_visible()
            calls.clear();page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#withdraw-consultation').click()
            expect(page.locator('#withdraw-consultation')).to_be_disabled()
            # A programmatic second click must not bypass the busy guard.
            page.locator('#withdraw-consultation').dispatch_event('click')
            for _ in range(50):
                if held_withdraw:break
                page.wait_for_timeout(20)
            assert len(held_withdraw)==1
            page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'))")
            waiting,payload=held_withdraw.pop()
            waiting.fulfill(status=200,content_type='application/json',body=json.dumps(payload))
            page.wait_for_timeout(150)
            expect(page.locator('#content')).to_be_hidden()
            expect(page.locator('#consultation-status')).to_have_text('')
            for field in fields:expect(page.locator('#profile-'+field)).to_have_text('')
            assert sum(path.endswith('/withdraw') for path,_,_ in calls)==1
            # A CSRF response arriving after pagehide must not start a write.
            scenario.update(hold_withdraw=False,hold_csrf=True)
            page.reload();expect(page.locator('#withdraw-consultation')).to_be_visible()
            calls.clear();page.once('dialog',lambda dialog:dialog.accept())
            page.locator('#withdraw-consultation').click()
            for _ in range(50):
                if held_csrf:break
                page.wait_for_timeout(20)
            assert len(held_csrf)==1
            page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'))")
            waiting,payload=held_csrf.pop()
            waiting.fulfill(status=200,content_type='application/json',body=json.dumps(payload))
            page.wait_for_timeout(150)
            assert not any(path.endswith('/withdraw') for path,_,_ in calls)
            scenario.update(hold_csrf=False,registration={**record,'consultation_consent':False})
            page.reload();expect(page.locator('.order-card')).to_have_count(2)
            expect(page.locator('#withdraw-consultation')).to_be_hidden()
            print('PASS: optional withdrawal capability, cancel, scoped request, success, 401/403/503, repeat-click guard, stale mutation and CSRF results. Synthetic only.')
            browser.close()
        print('PASS: isolated UI checks: desktop/mobile, tabs, search, pagination, access gates, error/retry, XSS text rendering, logout data clearing; required/optional profile at 320/390/1280px, legacy mode, null/unknown values, stale response. No real API or DB used.')
    finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
