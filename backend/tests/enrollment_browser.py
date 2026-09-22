"""Synthetic UI integration: localhost only, no auth provider/cloud/real DB."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit, parse_qs
import json

from playwright.sync_api import sync_playwright, expect

STATIC=Path(__file__).resolve().parents[1]/'enrollment_static'
DATA=[dict(enrollment_id=f'00000000-0000-4000-8000-{i:012d}',learner_id=str(i),
           full_name=f'가상수강생 {i:02d}',nickname='테스트 닉네임',course_id='demo-course',course_title='가상 리치온',cohort='검증용',
           latest_plan_months=(1,3,12)[i%3],total_months=(1,3,12)[i%3],starts_on='2026-10-01',
           ends_on='2026-10-31',remaining_days=5,enrollment_status='active',
           latest_agreed_amount_krw=1000,latest_discount_krw=0,paid_amount_krw=None,
           email_masked='s***@example.invalid',phone_masked='010-****-0000',
           cash_receipt_requested=True,cash_receipt_status='unverified',
           applied_at='2026-09-22T00:00:00Z',joined_at=None,confirmed_term_count=1,
           pending_term_count=0,agreed_total_krw=1000) for i in range(1,26)]
DATA[0]['nickname']='<img src=x onerror="window.injected=true">'


def result(url):
    q=parse_qs(urlsplit(url).query)
    rows=DATA
    if q.get('months'): rows=[r for r in rows if str(r['latest_plan_months'])==q['months'][0]]
    if q.get('q'): rows=[r for r in rows if q['q'][0] in r['full_name']]
    offset=int(q.get('offset',['0'])[0]);limit=int(q.get('limit',['20'])[0]);n=len(rows)
    return dict(as_of='2026-10-27',items=rows[offset:offset+limit],limit=limit,offset=offset,has_more=offset+limit<n,
                summary=dict(enrollment_count=n,learner_count=n,active_learners=n,scheduled_enrollments=0,
                             ending_soon=n,pending_enrollments=0,needs_review=0),courses_truncated=False,
                courses=[dict(course_id='demo-course',course_title='가상 리치온',cohort='검증용',active_learners=n,scheduled_enrollments=0,matching_enrollments=n)] if n else [])


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def do_GET(self):
        path=urlsplit(self.path).path
        name='enrollments.html' if path=='/portal/admin/enrollments' else path.rsplit('/',1)[-1]
        if name not in ('enrollments.html','enrollments.css','enrollments.js'):
            self.send_error(404);return
        content=(STATIC/name).read_bytes();self.send_response(200)
        self.send_header('Content-Type',{'html':'text/html','css':'text/css','js':'application/javascript'}[name.rsplit('.',1)[1]]+'; charset=utf-8')
        self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
            mode={'status':200}
            def respond(route):
                route.fulfill(status=mode['status'],content_type='application/json',body=json.dumps(result(route.request.url) if mode['status']==200 else {'detail':'unavailable'},ensure_ascii=False))
            page.route('**/portal/api/admin/enrollments?*',respond)
            page.route('**/auth/csrf',lambda r:r.fulfill(status=401,content_type='application/json',body='{}'))
            page.goto(f'http://127.0.0.1:{server.server_port}/portal/admin/enrollments')
            expect(page.locator('#rows tr')).to_have_count(20)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#rows img').count()==0 and page.evaluate('window.injected') is None
            page.locator('#next').click();expect(page.locator('#rows tr')).to_have_count(5)
            page.locator('#previous').click();expect(page.locator('#rows tr')).to_have_count(20)
            page.select_option('select[name=months]','3');page.get_by_role('button',name='조회하기').click()
            expect(page.locator('#rows tr')).to_have_count(9)
            page.get_by_text('표시할 열',exact=True).click()
            page.locator('#column-options').get_by_label('닉네임',exact=True).uncheck()
            assert page.locator('th[data-col=nickname]').is_hidden()
            page.get_by_text('표시할 열',exact=True).click()
            page.locator('input[name=q]').fill('no-match');page.get_by_role('button',name='조회하기').click()
            expect(page.locator('#rows tr')).to_have_count(0);expect(page.locator('#notice')).to_contain_text('조건에 맞는')
            page.get_by_role('button',name='초기화').click();expect(page.locator('#rows tr')).to_have_count(20)
            for width in (320,390,768,1440):
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'Overflow: {width}'
            for code,text in [(401,'로그인이 필요'),(403,'관리자 권한'),(503,'불러오지 못')]:
                mode['status']=code;page.locator('#refresh').click();expect(page.locator('#notice')).to_contain_text(text)
                expect(page.locator('#rows tr')).to_have_count(0)
            mode['status']=200;page.locator('#refresh').click();expect(page.locator('#rows tr')).to_have_count(20)
            page.locator('#logout').click();expect(page.locator('#notice')).to_contain_text('로그아웃 상태')
            expect(page.locator('#rows tr')).to_have_count(0)
            assert not errors,errors
            browser.close()
        print('PASS: synthetic enrollment UI desktop/mobile, filters, pagination, columns, XSS, access/error gates, logout clearing; no real backend/DB used.')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__': main()
