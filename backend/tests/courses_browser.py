"""Synthetic course/session admin UI regression. No real login, DB, provider or customer data."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit
import sys

from playwright.sync_api import sync_playwright, expect

STATIC=Path(__file__).resolve().parents[1]/'portal_static'
RUN_ID='00000000-0000-4000-8000-000000000101'
SESSION_ID='00000000-0000-4000-8000-000000000201'

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name={
            '/portal/courses':'courses.html',
            '/portal/assets/site.css':'site.css',
            '/portal/assets/site.js':'site.js',
            '/portal/assets/ops.css':'ops.css',
            '/portal/assets/ops.js':'ops.js',
            '/portal/assets/portal.css':'portal.css',
            '/portal/course-assets/courses.css':'courses.css',
            '/portal/course-assets/courses.js':'courses.js',
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
    programs=[{'program_id':'pre-richon','title':'Pre리치온','description':'가상','access_mode':'fixed_months','fixed_months':2,'archived':False,'version':1}]
    runs=[{'run_id':RUN_ID,'program_id':'pre-richon','program_title':'Pre리치온','cohort_label':'Pre리치온 9기',
           'starts_on':'2026-10-08','ends_on':'2026-12-07','default_access_start':'2026-10-08','default_access_end':'2026-12-07',
           'recruit_opens_at':None,'recruit_closes_at':None,'capacity':None,'status':'OPEN','price_krw':176000,
           'archived':False,'version':1,'enrollment_count':0}]
    sessions=[{'session_id':SESSION_ID,'run_id':RUN_ID,'sequence_no':1,'title':'부동산 투자원칙','mentor_name':'이루민',
               'starts_at':'2026-10-08T12:00:00+00:00','ends_at':'2026-10-08T14:00:00+00:00',
               'video_url':None,'material_url':None,'content_url':None,'cancelled':False,'version':1}]
    enrollments=[
      {'enrollment_id':'00000000-0000-4000-8000-000000000401','run_id':RUN_ID,'learner_id':'00000000-0000-4000-8000-000000000501',
       'member_id':'00000000-0000-4000-8000-000000000601','name':'가상 취소회원','phone_masked':None,'email_masked':None,
       'program_title':'Pre리치온','cohort_label':'Pre리치온 9기','access_start':'2026-10-08','access_end':'2026-12-07',
       'source':'ADMIN','note':None,'version':2,'status':'CANCELLED'},
      {'enrollment_id':'00000000-0000-4000-8000-000000000402','run_id':RUN_ID,'learner_id':'00000000-0000-4000-8000-000000000502',
       'member_id':'00000000-0000-4000-8000-000000000602','name':'가상 중지회원','phone_masked':None,'email_masked':None,
       'program_title':'Pre리치온','cohort_label':'Pre리치온 9기','access_start':'2026-10-08','access_end':'2026-12-07',
       'source':'ADMIN','note':None,'version':3,'status':'SUSPENDED'},
    ]
    posts=[];counter=[300]
    try:
        with sync_playwright() as p:
            kwargs={'headless':True}
            if os.environ.get('RICHON_BROWSER_EXECUTABLE'):kwargs['executable_path']=os.environ['RICHON_BROWSER_EXECUTABLE']
            browser=p.chromium.launch(**kwargs);context=browser.new_context(viewport={'width':1440,'height':1100},locale='ko-KR')
            def route(req):
                u=urlsplit(req.request.url)
                if u.netloc!=urlsplit(origin).netloc:return req.abort()
                path=u.path
                if not(path.startswith('/portal/api/') or path.startswith('/auth/')):return req.continue_()
                method=req.request.method
                if path=='/portal/api/me':
                    data={'member_id':'00000000-0000-4000-8000-000000000001','display_name':'가상 운영자','role':'admin',
                          'created_at':'2026-10-01T00:00:00Z','providers':['kakao'],'linked_order_count':0}
                elif path=='/portal/api/admin/learning/programs' and method=='GET':
                    data={'items':programs,'limit':100,'offset':0,'has_more':False}
                elif path=='/portal/api/admin/learning/runs' and method=='GET':
                    data={'items':runs,'limit':100,'offset':0,'has_more':False}
                elif path=='/portal/api/admin/learning/enrollments' and method=='GET':
                    data={'items':[x.copy() for x in enrollments],'limit':100,'offset':0,'has_more':False}
                elif path=='/portal/api/admin/learning/sessions' and method=='GET':
                    data=[x.copy() for x in sessions]
                elif path=='/auth/csrf':
                    data={'csrf_token':'test-only'}
                elif path=='/portal/api/admin/learning/enrollments/restore' and method=='POST':
                    body=req.request.post_data_json;posts.append((path,body.copy()))
                    row=next(x for x in enrollments if x['enrollment_id']==body['enrollment_id'])
                    assert row['status'] in {'CANCELLED','SUSPENDED'}
                    row.update(status='ACTIVE',version=row['version']+1)
                    data={'enrollment_id':row['enrollment_id'],'version':row['version'],'status':'ACTIVE'}
                elif path=='/portal/api/admin/learning/enrollments/cancel' and method=='POST':
                    body=req.request.post_data_json;posts.append((path,body.copy()))
                    row=next(x for x in enrollments if x['enrollment_id']==body['enrollment_id'])
                    row.update(status='CANCELLED',version=row['version']+1)
                    data={'enrollment_id':row['enrollment_id'],'version':row['version'],'status':'CANCELLED'}
                elif path=='/portal/api/admin/learning/sessions/update' and method=='POST':
                    body=req.request.post_data_json;posts.append((path,body.copy()))
                    row=next(x for x in sessions if x['session_id']==body['session_id'])
                    row.update(title=body['title'],mentor_name=body.get('mentor_name'),starts_at=body['starts_at'],ends_at=body.get('ends_at'),
                               video_url=body.get('video_url'),material_url=body.get('material_url'),cancelled=body.get('cancelled',False),
                               version=row['version']+1)
                    data={'session_id':row['session_id'],'run_id':row['run_id'],'version':row['version'],'cancelled':row['cancelled']}
                elif path=='/portal/api/admin/learning/sessions' and method=='POST':
                    body=req.request.post_data_json;posts.append((path,body.copy()));counter[0]+=1
                    sid=f'00000000-0000-4000-8000-{counter[0]:012d}'
                    row={'session_id':sid,'run_id':body['run_id'],'sequence_no':body['sequence_no'],'title':body['title'],
                         'mentor_name':body.get('mentor_name'),'starts_at':body['starts_at'],'ends_at':body.get('ends_at'),
                         'video_url':body.get('video_url'),'material_url':body.get('material_url'),'content_url':None,
                         'cancelled':False,'version':1}
                    sessions.append(row);data={'session_id':sid,'run_id':body['run_id'],'version':1}
                else:
                    raise AssertionError('unexpected API '+method+' '+path)
                req.fulfill(status=200,content_type='application/json',body=json.dumps(data))
            context.route('**/*',route)
            page=context.new_page();page.goto(origin+'/portal/courses')
            expect(page.locator('#gate')).to_be_hidden()
            expect(page.locator('#session-run')).to_have_value(RUN_ID)
            expect(page.locator('.session-card')).to_have_count(1)
            expect(page.locator('.session-card')).to_contain_text('1회 · 부동산 투자원칙')
            expect(page.locator('.session-card')).to_contain_text('멘토 이루민')

            page.locator('.session-card button',has_text='수정').click()
            expect(page.locator('#session-form [name=sequence_no]')).to_have_value('1')
            expect(page.locator('#session-form [name=sequence_no]')).to_be_disabled()
            expect(page.locator('#session-form [name=starts_at]')).to_have_value('2026-10-08T21:00')
            page.locator('#session-form [name=video_url]').fill('https://example.invalid/video')
            page.locator('#session-form [name=material_url]').fill('https://example.invalid/material')
            page.locator('#session-save').click()
            expect(page.locator('#session-status')).to_have_text('회차를 수정했습니다.')
            assert posts[-1][0].endswith('/update') and 'sequence_no' not in posts[-1][1]
            expect(page.locator('.session-resource',has_text='영상 보기')).to_have_attribute('href','https://example.invalid/video')
            expect(page.locator('.session-resource',has_text='자료 보기')).to_have_attribute('href','https://example.invalid/material')

            expect(page.locator('#session-form [name=sequence_no]')).to_be_enabled()
            page.locator('#session-form [name=sequence_no]').fill('2')
            page.locator('#session-form [name=title]').fill('갭투자')
            page.locator('#session-form [name=mentor_name]').fill('가상 멘토')
            page.locator('#session-form [name=starts_at]').fill('2026-10-15T21:00')
            page.locator('#session-save').click()
            expect(page.locator('#session-status')).to_have_text('회차를 추가했습니다.')
            expect(page.locator('.session-card')).to_have_count(2)
            assert posts[-1][1]['sequence_no']==2 and posts[-1][1]['starts_at']=='2026-10-15T21:00:00+09:00'

            page.on('dialog',lambda dialog:dialog.accept())
            first=page.locator('.session-card').first
            first.locator('button',has_text='사용 중지').click()
            expect(first).to_contain_text('사용 중지됨')
            first.locator('button',has_text='복구').click()
            expect(page.locator('.session-card').first).to_contain_text('사용 중')

            expect(page.locator('#enrollment-body tr')).to_have_count(2)
            cancelled=page.locator('#enrollment-body tr').filter(has_text='가상 취소회원')
            suspended=page.locator('#enrollment-body tr').filter(has_text='가상 중지회원')
            expect(cancelled.locator('button')).to_have_text('복구')
            expect(suspended.locator('button')).to_have_text('재개')

            cancelled.locator('button').click()
            expect(page.locator('#enrollment-status')).to_have_text('수강권을 복구했습니다.')
            expect(page.locator('#enrollment-body tr').filter(has_text='가상 취소회원')).to_contain_text('ACTIVE')
            assert posts[-1][0].endswith('/enrollments/restore')
            assert posts[-1][1]['reason']=='관리자 수강권 복구'

            page.locator('#enrollment-body tr').filter(has_text='가상 중지회원').locator('button').click()
            expect(page.locator('#enrollment-status')).to_have_text('수강권을 재개했습니다.')
            expect(page.locator('#enrollment-body tr').filter(has_text='가상 중지회원')).to_contain_text('ACTIVE')
            assert posts[-1][0].endswith('/enrollments/restore')
            assert posts[-1][1]['reason']=='관리자 수강권 재개'

            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            if len(sys.argv)>1:
                dst=Path(sys.argv[1]);dst.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(dst/'courses-mobile.png'),full_page=True)
            browser.close()
        print('PASS: admin course sessions/resources, enrollment cancel restore/resume and mobile layout; synthetic only.')
    finally:
        server.shutdown();server.server_close()

if __name__=='__main__':main()
