"""Real Chromium native-form Origin regression, entirely intercepted/offline.
No Cloudflare login, real Kakao/Naver request, database or user credentials.
"""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from test_oauth import settings
import oauth_http as h
import oauth_store as store
from auth_core import VerifiedIdentity
from portal_entry import EdgeBoundary

ORIGIN='https://localhost'
KEY='E'*43


def browser_case(browser, *, legacy=False, signup=False, screenshot=None):
    cfg=replace(settings(),origin=ORIGIN)
    app=FastAPI();app.include_router(h.make_router(cfg))
    app.add_middleware(EdgeBoundary,enabled=True,secret=KEY)
    captured=[]
    context=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844})
    if signup:
        context.add_cookies([{'name':name,'value':value,'url':ORIGIN,'secure':True,'httpOnly':True,'sameSite':'Lax'}
                            for name,value in [(h.BROWSER,'B'*43),(h.TICKET,'T'*43)]])
    def intercept(route):
        request=route.request;url=urlsplit(request.url)
        assert url.scheme+'://'+url.netloc==ORIGIN, 'Unexpected network request blocked'
        if url.path in ('/','/apply.html'):
            route.fulfill(status=200,content_type='text/html',body='<h1>RETURNED</h1>');return
        headers=dict(request.all_headers());headers['X-Richon-Edge-Key']=KEY
        # Inject only the synthetic transport edge key, never fabricate Origin.
        with TestClient(app,base_url=ORIGIN) as client:
            response=client.request(request.method,request.url,headers=headers,
                                    content=request.post_data_buffer,follow_redirects=False)
        outgoing=dict(response.headers)
        if legacy and request.method=='GET' and url.path in ('/auth/login','/auth/signup'):
            outgoing['referrer-policy']='no-referrer'
        if request.method=='POST':
            captured.append((url.path,headers.get('origin'),response.status_code))
        if url.path=='/auth/start' and response.status_code==303:
            assert response.headers['location'].startswith('https://kauth.kakao.com/oauth/authorize?')
            route.fulfill(status=200,content_type='text/html',body='<h1>MOCK PROVIDER REDIRECT CAPTURED</h1>')
        else:
            route.fulfill(status=response.status_code,headers=outgoing,body=response.content)
    context.route('**/*',intercept)
    page=context.new_page()
    identity=VerifiedIdentity('kakao','1585992','synthetic-browser','테스트')
    try:
        with patch.object(store,'begin',return_value='S'*43), \
             patch.object(store,'pending',return_value=(identity,'/apply.html')), \
             patch.object(h.core,'register_verified_identity',return_value=uuid4()), \
             patch.object(h,'complete',side_effect=lambda member,request,target:h.redirect(target)):
            page.goto(ORIGIN+('/auth/signup' if signup else '/auth/login?return_to=%2Fapply.html'))
            if screenshot:page.screenshot(path=screenshot,full_page=True)
            if signup:
                page.check('input[name=terms]');page.check('input[name=privacy]')
            page.locator('button').first.click()
            page.wait_for_timeout(250)
        expected_path='/auth/signup' if signup else '/auth/start'
        assert captured==[(expected_path,'null' if legacy else ORIGIN,403 if legacy else 303)], captured
        if not legacy and signup:
            assert page.url==ORIGIN+'/apply.html'
        print('PASS: '+('signup' if signup else 'login')+' native form / '+('legacy null Origin reproduced' if legacy else 'real same-origin Origin accepted'))
    finally:
        context.close()


def main():
    with sync_playwright() as p:
        options={'headless':True}
        if os.getenv('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
        browser=p.chromium.launch(**options)
        try:
            for signup in (False,True):
                browser_case(browser,legacy=True,signup=signup)
                browser_case(browser,signup=signup,screenshot=os.getenv('LOGIN_SCREENSHOT') if not signup else None)
        finally:browser.close()
    print('4 browser scenarios passed. All provider and database operations were mocked.')


if __name__=='__main__':main()
