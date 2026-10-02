"""Synthetic visual calendar regression. No real login, DB, provider or customer data."""
import json
import os
import re
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit, parse_qs
import sys

from playwright.sync_api import sync_playwright, expect

STATIC=Path(__file__).resolve().parents[1]/'portal_static'
PRE_ID='00000000-0000-4000-8000-000000000020'

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
            '/portal/calendar-assets/calendar-logo.svg':'calendar-logo.svg',
        }.get(urlsplit(self.path).path)
        if not name:self.send_error(404);return
        content=(STATIC/name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','svg':'image/svg+xml'}[name.rsplit('.',1)[1]])
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
    def log_message(self,*args):pass

def visible_in_month(row,month):
    if row.get('display_kind')!='BANNER':
        return row['event_date'].startswith(month)
    start=month+'-01'
    y,m=map(int,month.split('-'))
    next_month=f'{y+1:04d}-01-01' if m==12 else f'{y:04d}-{m+1:02d}-01'
    return row['event_date']<next_month and (row.get('end_date') or row['event_date'])>=start

def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    items=[
        {'item_id':PRE_ID,'event_id':PRE_ID,'display_kind':'EVENT','event_date':'2026-10-08','end_date':None,
         'color_hex':'#00B622','course_label':'Pre리치온','content_text':'부동산 기초 및 시장구조','version':1},
        {'item_id':'00000000-0000-4000-8000-000000000021','event_id':'00000000-0000-4000-8000-000000000021',
         'display_kind':'EVENT','event_date':'2026-10-05','end_date':None,'color_hex':'#D8BD78',
         'course_label':'리치온 아카데미','content_text':'무료 브리핑','version':1},
        {'item_id':'00000000-0000-4000-8000-000000000022','event_id':'00000000-0000-4000-8000-000000000022',
         'display_kind':'EVENT','event_date':'2026-10-04','end_date':None,'color_hex':'#FF5757',
         'course_label':'리치온 실전투자','content_text':'멘토 키네스트','version':1},
        {'item_id':'00000000-0000-4000-8000-000000000023','event_id':'00000000-0000-4000-8000-000000000023',
         'display_kind':'BANNER','event_date':'2026-10-09','end_date':'2026-10-12','color_hex':'#FF5757',
         'course_label':'리치온 아카데미','content_text':'','version':1},
    ]
    posts=[];counter=[30]
    try:
        with sync_playwright() as p:
            kwargs={'headless':True}
            if os.environ.get('RICHON_BROWSER_EXECUTABLE'):kwargs['executable_path']=os.environ['RICHON_BROWSER_EXECUTABLE']
            browser=p.chromium.launch(**kwargs);context=browser.new_context(viewport={'width':1440,'height':1100},locale='ko-KR')
            context.add_init_script("""
                Object.defineProperty(window,'ClipboardItem',{value:class ClipboardItem {
                  constructor(data){this.data=data;this.types=Object.keys(data);}
                }});
                Object.defineProperty(navigator,'clipboard',{value:{write:async items=>{
                  window.__clipboardItems=items;
                  window.__clipboardBlob=items[0].data['image/png'];
                }}});
            """)
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
                    data={'month':month,'items':[x.copy() for x in items if visible_in_month(x,month)]}
                elif path=='/auth/csrf':
                    data={'csrf_token':'test-only'}
                elif path=='/portal/api/admin/learning/calendar-events' and method=='POST':
                    body=route.request.post_data_json;posts.append((path,body.copy()))
                    counter[0]+=1;eid=f'00000000-0000-4000-8000-{counter[0]:012d}'
                    row={'item_id':eid,'event_id':eid,'display_kind':body['display_kind'],'event_date':body['event_date'],
                         'end_date':body.get('end_date'),'color_hex':body['color_hex'],'course_label':body['course_label'],
                         'content_text':body.get('content_text',''),'version':1}
                    items.append(row);data={'event_id':eid,'version':1}
                elif path=='/portal/api/admin/learning/calendar-events/update' and method=='POST':
                    body=route.request.post_data_json;posts.append((path,body.copy()))
                    row=next(x for x in items if x['event_id']==body['event_id'])
                    if body.get('deleted'):
                        items.remove(row);data={'event_id':body['event_id'],'version':row['version']+1,'deleted':True}
                    else:
                        row.update(display_kind=body['display_kind'],event_date=body['event_date'],end_date=body.get('end_date'),
                                   color_hex=body['color_hex'],course_label=body['course_label'],
                                   content_text=body.get('content_text',''),version=row['version']+1)
                        data={'event_id':row['event_id'],'version':row['version'],'deleted':False}
                else:
                    raise AssertionError('unexpected API '+method+' '+path)
                route.fulfill(status=200,content_type='application/json',body=json.dumps(data))
            context.route('**/*',api_route)
            page=context.new_page();page.goto(origin+'/portal/calendar')
            expect(page.locator('#gate')).to_be_hidden()
            expect(page.locator('#month-label')).to_have_text('2026년 10월')
            for button_id in ('prev-month','next-month'):
                button=page.locator('#'+button_id)
                box=button.bounding_box()
                assert box and box['width']>=44 and box['height']>=44
                assert button.locator('span').evaluate("(el)=>getComputedStyle(el).pointerEvents")=='none'
                center=page.evaluate("""id=>{
                  const el=document.getElementById(id),r=el.getBoundingClientRect();
                  return document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.id||'';
                }""",button_id)
                assert center==button_id
            expect(page.locator('.calendar-logo')).to_have_attribute('src','/portal/calendar-assets/calendar-logo.svg')
            assert page.locator('.calendar-logo').evaluate("(el)=>el.complete&&el.naturalWidth>0")
            # Legend must not shift the title: the title block stays centered on the calendar paper.
            centers=page.evaluate("""()=>{
              const paper=document.querySelector('.calendar-paper').getBoundingClientRect();
              const title=document.querySelector('.calendar-paper-title').getBoundingClientRect();
              return {paper:paper.left+paper.width/2,title:title.left+title.width/2};
            }""")
            assert abs(centers['paper']-centers['title'])<=1.0
            spacing=page.evaluate("""()=>{
              const title=document.querySelector('.calendar-paper-title').getBoundingClientRect();
              const weekdays=document.querySelector('.calendar-weekdays').getBoundingClientRect();
              return weekdays.top-title.bottom;
            }""")
            assert spacing>=20
            long_text=page.locator('[data-date="2026-10-08"] .event-content')
            expect(long_text).to_have_text('부동산 기초 및 시장구조')
            assert long_text.evaluate("(el)=>getComputedStyle(el).whiteSpace")=='nowrap'
            expect(page.locator('.calendar-week')).to_have_count(5)
            expect(page.locator('.calendar-event-item')).to_have_count(3)
            # Exact regression: 9~12 must never visually expand to the 8th.
            expect(page.locator('.holiday-day')).to_have_count(4)
            expect(page.locator('[data-date="2026-10-08"]')).not_to_have_class(re.compile(r'holiday-day'))
            # Proposal B: plain colored dates + one labeled ribbon on the first tied row + one blank continuation ribbon.
            expect(page.locator('.calendar-holiday-ribbon')).to_have_count(2)
            expect(page.locator('.calendar-holiday-ribbon.has-label')).to_have_count(1)
            expect(page.locator('.calendar-holiday-ribbon.has-label')).to_have_text('리치온 아카데미')
            expect(page.locator('.calendar-holiday-ribbon.is-continuation')).to_have_count(1)
            expect(page.locator('.calendar-holiday-ribbon.is-continuation')).to_have_text('')
            labeled=page.locator('.calendar-holiday-ribbon.has-label')
            assert labeled.evaluate("(el)=>el.style.gridColumnStart")=='6'
            assert labeled.evaluate("(el)=>el.style.gridColumnEnd")=='span 2'
            continuation=page.locator('.calendar-holiday-ribbon.is-continuation')
            assert continuation.evaluate("(el)=>el.style.gridColumnStart")=='1'
            assert continuation.evaluate("(el)=>el.style.gridColumnEnd")=='span 2'
            assert page.locator('[data-date="2026-10-09"]').evaluate("(el)=>getComputedStyle(el).backgroundColor")=='rgba(0, 0, 0, 0)'
            assert page.locator('[data-date="2026-10-09"] .calendar-date').evaluate("(el)=>getComputedStyle(el).backgroundColor")=='rgba(0, 0, 0, 0)'
            # Legend uses the actual monthly course text and each event's actual selected color.
            legend=page.locator('#calendar-legend .calendar-legend-item')
            expect(legend).to_have_count(3)
            expect(legend.nth(0)).to_have_text('리치온 실전투자')
            expect(legend.nth(0)).to_have_attribute('data-color','#FF5757')
            expect(legend.nth(0).locator('.calendar-legend-dot')).to_have_class(re.compile(r'color-red'))
            expect(legend.nth(1)).to_have_text('리치온 아카데미')
            expect(legend.nth(1)).to_have_attribute('data-color','#D8BD78')
            expect(legend.nth(1).locator('.calendar-legend-dot')).to_have_class(re.compile(r'color-gold'))
            expect(legend.nth(2)).to_have_text('Pre리치온')
            expect(legend.nth(2)).to_have_attribute('data-color','#00B622')
            expect(legend.nth(2).locator('.calendar-legend-dot')).to_have_class(re.compile(r'color-green'))
            expect(page.locator('#calendar-legend')).not_to_contain_text('무료 브리핑')
            expect(page.locator('#calendar-legend')).not_to_contain_text('리치온 스터디')
            expect(page.locator('#calendar-legend')).not_to_contain_text('재개발중급반')
            expect(page.locator('#copy-event')).to_have_text('일정 복제')

            # Export is a 1200x1200 PNG copied to the image clipboard, not a screenshot of admin chrome.
            page.locator('#copy-png').click()
            expect(page.locator('#copy-png')).to_have_text('✓ 복사 완료')
            expect(page.locator('#copy-png')).to_have_class(re.compile(r'is-success'))
            expect(page.locator('#action-status')).to_have_text('1200×1200 PNG 이미지를 클립보드에 복사했습니다.')
            png=page.evaluate("""async()=>{
              const blob=window.__clipboardBlob;
              const bitmap=await createImageBitmap(blob);
              return {type:blob.type,width:bitmap.width,height:bitmap.height,size:blob.size};
            }""")
            assert png['type']=='image/png' and png['width']==1200 and png['height']==1200 and png['size']>1000

            # Empty date click opens the compact editor with that date prefilled.
            page.locator('[data-date="2026-10-15"]').click()
            expect(page.locator('#calendar-editor')).to_be_visible()
            expect(page.locator('[name=event_date]')).to_have_value('2026-10-15')
            page.locator('#cancel-editor').click()

            # Copy is driven by the target date selected by the operator.
            page.locator('[data-date="2026-10-08"] .calendar-event-item').click()
            expect(page.locator('#editor-title')).to_have_text('일정 수정')
            expect(page.locator('[name=course_label]')).to_have_value('Pre리치온')
            page.locator('[name=event_date]').fill('2026-10-21')
            page.locator('#copy-event').click()
            expect(page.locator('#editor-status')).to_have_text('선택한 날짜에 복사했습니다.')
            expect(page.locator('.calendar-event-item')).to_have_count(4)
            assert posts[-1][1]['event_date']=='2026-10-21'
            assert posts[-1][1]['display_kind']=='EVENT'
            expect(page.locator('[name=event_date]')).to_have_value('2026-10-21')

            # The copy stays selected, so it can be copied again to any date.
            page.locator('[name=event_date]').fill('2026-11-19')
            page.locator('#copy-event').click()
            expect(page.locator('#month-label')).to_have_text('2026년 11월')
            assert posts[-1][1]['event_date']=='2026-11-19'

            # Free text remains text, never HTML.
            page.locator('[name=content_text]').fill('<img src=x onerror=alert(1)> 자유 텍스트')
            page.locator('#save-event').click()
            expect(page.locator('.calendar-weeks')).to_contain_text('<img src=x onerror=alert(1)> 자유 텍스트')
            assert page.locator('.calendar-weeks img').count()==0

            # Holiday/emphasis entry accepts a date range and renders across columns.
            page.locator('#add-event').click()
            page.locator('[data-calendar-kind="BANNER"]').click()
            page.locator('[name=event_date]').fill('2026-11-23')
            page.locator('[name=end_date]').fill('2026-11-26')
            page.locator('[name=color_hex]').select_option('#FF5757')
            page.locator('[name=course_label]').fill('추석연휴')
            page.locator('#save-event').click()
            expect(page.locator('.calendar-holiday-ribbon.has-label').filter(has_text='추석연휴')).to_have_count(1)
            assert posts[-1][1]['display_kind']=='BANNER'
            assert posts[-1][1]['end_date']=='2026-11-26'

            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            expect(page.locator('.calendar-weeks')).to_be_hidden()
            expect(page.locator('#calendar-mobile-list')).to_be_visible()
            expect(page.locator('.mobile-banner')).to_contain_text('11/23–11/26 추석연휴')
            if len(sys.argv)>1:
                dst=Path(sys.argv[1]);dst.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(dst/'calendar-mobile.png'),full_page=True)
            browser.close()
        print('PASS: original SVG logo, title centered independently of legend, proposal-B holiday ribbons, actual monthly legend, visible PNG copy success and 1200px export; synthetic only.')
    finally:
        server.shutdown();server.server_close()

if __name__=='__main__':main()
