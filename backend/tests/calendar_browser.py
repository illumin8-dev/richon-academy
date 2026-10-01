"""Synthetic central-calendar browser regression. No real login, DB, provider or customer data."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit, parse_qs
import sys

from playwright.sync_api import sync_playwright, expect

STATIC=Path(__file__).resolve().parents[1]/'portal_static'
RUN_ID='00000000-0000-4000-8000-000000000010'
SESSION_ID='00000000-0000-4000-8000-000000000020'

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name={
            '/portal/calendar':'calendar.html',
            '/portal/assets/site.css':'site.css',
            '/portal/assets/site.js':'site.js',
            '/portal/assets/ops.css':'ops.css',
            '/portal/assets/portal.css':'portal.css',
            '/portal/calendar-assets/calendar.css':'calendar.css',
            '/portal/calendar-assets/calendar.js':'calendar.js',
        }.get(urlsplit(self.path).path)
        if not name:self.send_error(404);return
        content=(STATIC/name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.rsplit('.',1)[1]])
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
    def log_message(self,*args):pass

def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    posts=[]
    try:
        with sync_playwright() as p:
            kwargs={'headless':True}
            if os.environ.get('RICHON_BROWSER_EXECUTABLE'):kwargs['executable_path']=os.environ['RICHON_BROWSER_EXECUTABLE']
            browser=p.chromium.launch(**kwargs);context=browser.new_context(viewport={'width':1440,'height':1100},locale='ko-KR')
            def route(route):
                u=urlsplit(route.request.url)
                if u.netloc!=urlsplit(origin).netloc:return route.abort()
                path=u.path
                if not(path.startswith('/portal/api/') or path.startswith('/auth/')):return route.continue_()
                if path=='/portal/api/me':data={'member_id':'00000000-0000-4000-8000-000000000001','display_name':'가상 운영자','role':'admin','created_at':'2026-10-01T00:00:00Z','providers':['kakao'],'linked_order_count':0}
                elif path=='/portal/api/admin/learning/programs':data={'items':[{'program_id':'pre-richon','title':'Pre리치온','access_mode':'fixed_months','fixed_months':2,'archived':False,'version':1}],'limit':100,'offset':0,'has_more':False}
                elif path=='/portal/api/admin/learning/runs':data={'items':[{'run_id':RUN_ID,'program_id':'pre-richon','program_title':'Pre리치온','cohort_label':'가상 10월반','starts_on':'2026-10-01','ends_on':'2026-11-30','default_access_start':'2026-10-01','default_access_end':'2026-11-30','status':'OPEN','price_krw':0,'capacity':None,'archived':False,'version':1}],'limit':100,'offset':0,'has_more':False}
                elif path=='/portal/api/admin/learning/calendar':
                    month=parse_qs(u.query).get('month',['2026-10'])[0]
                    data={'month':month,'items':[{'kind':'session','item_id':SESSION_ID,'session_id':SESSION_ID,'event_id':None,'run_id':RUN_ID,'sequence_no':1,'program_id':'pre-richon','category_label':'Pre리치온','cohort_label':'가상 10월반','event_type':None,'title':'부동산 투자원칙','presenter_name':'가상 멘토','starts_at':month+'-08T12:00:00Z','ends_at':month+'-08T14:00:00Z','is_public':True,'cancelled':False,'version':1,'video_url':None,'material_url':None}]}
                elif path=='/auth/csrf':data={'csrf_token':'test-only'}
                elif route.request.method=='POST':
                    posts.append((path,route.request.post_data_json));data={'ok':True}
                else:raise AssertionError('unexpected '+path)
                route.fulfill(status=200,content_type='application/json',body=json.dumps(data))
            context.route('**/*',route)
            page=context.new_page();page.goto(origin+'/portal/calendar')
            expect(page.locator('#gate')).to_be_hidden();expect(page.locator('#calendar-grid .calendar-event')).to_have_count(1)
            page.locator('#calendar-grid .calendar-event').click()
            expect(page.locator('#editor-title')).to_have_text('일정 수정')
            expect(page.locator('#calendar-form [name=sequence_no]')).to_have_value('1')
            before=page.locator('#calendar-form [name=date]').input_value()
            page.locator('#clone-week').click()
            expect(page.locator('#editor-title')).to_have_text('복제한 새 일정')
            expect(page.locator('#calendar-form [name=sequence_no]')).to_have_value('2')
            after=page.locator('#calendar-form [name=date]').input_value()
            assert before!=after
            page.locator('#calendar-form [name=title]').fill('<img src=x onerror=alert(1)>')
            assert page.locator('#calendar-form img').count()==0
            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(80)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            expect(page.locator('#calendar-grid')).to_be_hidden();expect(page.locator('#calendar-agenda')).to_be_visible()
            if len(sys.argv)>1:
                dst=Path(sys.argv[1]);dst.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(dst/'calendar-mobile.png'),full_page=True)
            browser.close()
        print('PASS: central calendar desktop/mobile rendering, edit, next-week clone and XSS-safe text; synthetic only.')
    finally:
        server.shutdown();server.server_close()

if __name__=='__main__':main()
