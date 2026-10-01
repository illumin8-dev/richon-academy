"""Synthetic free-form calendar browser regression. No real login, DB or customer data."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit, parse_qs
import sys

from playwright.sync_api import sync_playwright, expect

STATIC=Path(__file__).resolve().parents[1]/'portal_static'
FIRST_ID='00000000-0000-4000-8000-000000000020'

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
    items=[{'item_id':FIRST_ID,'event_id':FIRST_ID,'event_date':'2026-10-08','color_hex':'#00B622',
            'course_label':'Pre리치온','content_text':'부동산 투자원칙','version':1}]
    posts=[]
    counter=[30]
    try:
        with sync_playwright() as p:
            kwargs={'headless':True}
            if os.environ.get('RICHON_BROWSER_EXECUTABLE'):kwargs['executable_path']=os.environ['RICHON_BROWSER_EXECUTABLE']
            browser=p.chromium.launch(**kwargs);context=browser.new_context(viewport={'width':1440,'height':1100},locale='ko-KR')
            def api_route(route):
                u=urlsplit(route.request.url)
                if u.netloc!=urlsplit(origin).netloc:return route.abort()
                path=u.path
                if not(path.startswith('/portal/api/') or path.startswith('/auth/')):return route.continue_()
                method=route.request.method
                if path=='/portal/api/me':
                    data={'member_id':'00000000-0000-4000-8000-000000000001','display_name':'가상 운영자','role':'admin',
                          'created_at':'2026-10-01T00:00:00Z','providers':['kakao'],'linked_order_count':0}
                elif path=='/portal/api/admin/learning/calendar' and method=='GET':
                    month=parse_qs(u.query).get('month',['2026-10'])[0]
                    data={'month':month,'items':[x.copy() for x in items if x['event_date'].startswith(month)]}
                elif path=='/auth/csrf':
                    data={'csrf_token':'test-only'}
                elif path=='/portal/api/admin/learning/calendar-events' and method=='POST':
                    body=route.request.post_data_json;posts.append((path,body.copy()))
                    counter[0]+=1;eid=f'00000000-0000-4000-8000-{counter[0]:012d}'
                    row={'item_id':eid,'event_id':eid,'event_date':body['event_date'],'color_hex':body['color_hex'],
                         'course_label':body['course_label'],'content_text':body['content_text'],'version':1}
                    items.append(row);data={'event_id':eid,'version':1}
                elif path=='/portal/api/admin/learning/calendar-events/update' and method=='POST':
                    body=route.request.post_data_json;posts.append((path,body.copy()))
                    row=next(x for x in items if x['event_id']==body['event_id'])
                    if body.get('deleted'):
                        items.remove(row);data={'event_id':body['event_id'],'version':row['version']+1,'deleted':True}
                    else:
                        row.update(event_date=body['event_date'],color_hex=body['color_hex'],
                                   course_label=body['course_label'],content_text=body['content_text'],
                                   version=row['version']+1)
                        data={'event_id':row['event_id'],'version':row['version'],'deleted':False}
                else:
                    raise AssertionError('unexpected API '+method+' '+path)
                route.fulfill(status=200,content_type='application/json',body=json.dumps(data))
            context.route('**/*',api_route)
            page=context.new_page();page.goto(origin+'/portal/calendar')
            expect(page.locator('#gate')).to_be_hidden()
            expect(page.locator('#calendar-grid .calendar-event')).to_have_count(1)
            for absent in ('[name=kind]','[name=run_id]','[name=sequence_no]','[name=start_time]','[name=end_time]','[name=presenter_name]','[name=video_url]'):
                expect(page.locator('#calendar-form '+absent)).to_have_count(0)

            page.locator('#calendar-grid .calendar-event').click()
            expect(page.locator('#editor-title')).to_have_text('일정 수정')
            expect(page.locator('[name=course_label]')).to_have_value('Pre리치온')
            expect(page.locator('[name=content_text]')).to_have_value('부동산 투자원칙')

            # Copy is driven by the date the operator chooses; there is no fixed +7-day rule.
            page.locator('[name=event_date]').fill('2026-10-21')
            page.locator('#copy-event').click()
            expect(page.locator('#calendar-grid .calendar-event')).to_have_count(2)
            assert posts[-1][0].endswith('/calendar-events')
            assert posts[-1][1]['event_date']=='2026-10-21'
            assert posts[-1][1]['course_label']=='Pre리치온'
            assert posts[-1][1]['content_text']=='부동산 투자원칙'

            # The freshly copied entry stays selected, so it can be copied to any other date again.
            page.locator('[name=event_date]').fill('2026-11-19')
            page.locator('#copy-event').click()
            expect(page.locator('#month-label')).to_have_text('2026년 11월')
            expect(page.locator('#calendar-grid .calendar-event')).to_have_count(1)
            assert posts[-1][1]['event_date']=='2026-11-19'

            page.locator('[name=color_hex]').select_option('#C000DB')
            page.locator('[name=course_label]').fill('완전 자유 과정')
            page.locator('[name=content_text]').fill('<img src=x onerror=alert(1)> 자유 텍스트')
            page.locator('#save-event').click()
            expect(page.locator('#calendar-grid')).to_contain_text('완전 자유 과정')
            expect(page.locator('#calendar-grid')).to_contain_text('<img src=x onerror=alert(1)> 자유 텍스트')
            assert page.locator('#calendar-grid img').count()==0

            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(80)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            expect(page.locator('#calendar-grid')).to_be_hidden();expect(page.locator('#calendar-agenda')).to_be_visible()
            if len(sys.argv)>1:
                dst=Path(sys.argv[1]);dst.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(dst/'calendar-mobile.png'),full_page=True)
            browser.close()
        print('PASS: free-form calendar fields, arbitrary-date copy, repeat copy, edit, XSS-safe text and mobile agenda; synthetic only.')
    finally:
        server.shutdown();server.server_close()

if __name__=='__main__':main()
