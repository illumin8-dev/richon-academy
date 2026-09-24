"""Chromium form/redirect regression with synthetic application inputs.
Application requests are intercepted. A loopback-only TLS landing fixture
handles the redirected URL, which Playwright does not intercept again.
No Cloudflare login, real Kakao/Naver request, database or user credentials.
"""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4
import os
import ssl
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_ui_fixture import shared_asset
from playwright.sync_api import sync_playwright
from test_oauth import settings
import oauth_http as h
import oauth_store as store
from auth_core import VerifiedIdentity
from portal_entry import EdgeBoundary

KEY='E'*43


@contextmanager
def landing_server():
    """Only a static landing page, bound to IPv4 loopback on an unused port.

    The self-signed key is created in a private temporary directory for this
    fixture, then deleted. It is never an account key or an uploaded artifact.
    """
    landed=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/', '/apply.html'):
                self.send_error(404);return
            landed.append(self.path)
            body=b'<h1>RETURNED</h1>'
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(body)
        def log_message(self,*args):
            pass
    with TemporaryDirectory(prefix='richon-browser-fixture-') as temporary:
        key=Path(temporary)/'loopback.key'
        cert=Path(temporary)/'loopback.crt'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes',
                        '-keyout',str(key),'-out',str(cert),'-days','1',
                        '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],
                       check=True,timeout=20,stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE,umask=0o077)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert,key)
        server.socket=tls.wrap_socket(server.socket,server_side=True)
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            yield 'https://localhost:'+str(server.server_port),landed
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            assert not thread.is_alive(), 'Loopback fixture did not stop'


def browser_case(browser, origin, landed, *, legacy=False, signup=False, screenshot=None):
    cfg=replace(settings(),origin=origin)
    app=FastAPI();app.include_router(h.make_router(cfg))
    app.add_middleware(EdgeBoundary,enabled=True,secret=KEY)
    captured=[];navigation=[];failures=[];console_errors=[]
    before=len(landed)
    context=browser.new_context(ignore_https_errors=True,service_workers='block',viewport={'width':390,'height':844})
    if signup:
        context.add_cookies([{'name':name,'value':value,'url':origin,'secure':True,'httpOnly':True,'sameSite':'Lax'}
                            for name,value in [(h.BROWSER,'B'*43),(h.TICKET,'T'*43)]])
    def intercept(route):
        if shared_asset(route, origin): return
        request=route.request;url=urlsplit(request.url)
        if url.scheme+'://'+url.netloc!=origin:
            route.abort('blockedbyclient')
            raise AssertionError('Unexpected network request blocked')
        navigation.append((request.method,url.path))
        if url.path in ('/','/apply.html'):
            route.continue_();return
        headers=dict(request.all_headers());headers['X-Richon-Edge-Key']=KEY
        # Inject only the synthetic transport edge key, never fabricate Origin.
        with TestClient(app,base_url=origin) as client:
            response=client.request(request.method,request.url,headers=headers,
                                    content=request.post_data_buffer,follow_redirects=False)
        outgoing=dict(response.headers)
        if legacy and request.method=='GET' and url.path in ('/auth/login','/auth/signup'):
            outgoing['referrer-policy']='no-referrer'
        if request.method=='POST':
            captured.append((url.path,headers.get('origin'),response.status_code,
                             urlsplit(response.headers.get('location','')).path))
        if url.path=='/auth/start' and response.status_code==303:
            assert response.headers['location'].startswith('https://kauth.kakao.com/oauth/authorize?')
            # Do not allow the browser to contact a real OAuth provider.
            route.fulfill(status=200,content_type='text/html',body='<h1>MOCK PROVIDER REDIRECT CAPTURED</h1>')
        else:
            if 300<=response.status_code<400:
                location=response.headers.get('location','')
                assert location=='/apply.html', 'Unexpected fixture redirect blocked'
            route.fulfill(status=response.status_code,headers=outgoing,body=response.content)
    context.route('**/*',intercept)
    page=context.new_page()
    page.on('requestfailed',lambda request:failures.append((urlsplit(request.url).path,request.failure)))
    page.on('console',lambda message:console_errors.append('csp' if 'Content Security Policy' in message.text or 'form-action' in message.text else 'browser-error') if message.type=='error' else None)
    identity=VerifiedIdentity('kakao','1585992','synthetic-browser','테스트')
    try:
        with patch.object(store,'begin',return_value='S'*43), \
             patch.object(store,'pending',return_value=(identity,'/apply.html')), \
             patch.object(h.core,'register_verified_identity',return_value=uuid4()), \
             patch.object(h,'complete',side_effect=lambda member,request,target:h.redirect(target)):
            page.goto(origin+('/auth/signup' if signup else '/auth/login?return_to=%2Fapply.html'))
            if screenshot:page.screenshot(path=screenshot,full_page=True)
            if signup:
                page.check('input[name=terms]');page.check('input[name=privacy]')
            page.locator('form button[type=submit]').first.click()
            if not legacy and signup:
                page.wait_for_url(origin+'/apply.html',wait_until='domcontentloaded',timeout=5000)
                assert page.locator('h1').inner_text()=='RETURNED'
            else:
                page.wait_for_load_state('domcontentloaded')
        expected_path='/auth/signup' if signup else '/auth/start'
        expected_location='' if legacy else ('/apply.html' if signup else '/oauth/authorize')
        assert captured==[(expected_path,'null' if legacy else origin,403 if legacy else 303,expected_location)], captured
        assert not failures, failures
        if not legacy and signup:
            assert page.url==origin+'/apply.html'
            assert landed[before:]==['/apply.html'], 'Final page must be loaded by the real redirect'
        else:
            assert len(landed)==before
        print('PASS: '+('signup' if signup else 'login')+' native form / '+('legacy null Origin reproduced' if legacy else 'real same-origin Origin accepted'))
    except Exception:
        print('LOCAL BROWSER DIAGNOSTIC:', {'legacy':legacy,'signup':signup,
              'page_path':urlsplit(page.url).path,'posts':captured,
              'intercepted_paths':navigation,'failures':failures,'console_categories':console_errors})
        raise
    finally:
        context.close()


def main():
    with landing_server() as (origin,landed), sync_playwright() as p:
        options={'headless':True}
        if os.getenv('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
        browser=p.chromium.launch(**options)
        try:
            for signup in (False,True):
                browser_case(browser,origin,landed,legacy=True,signup=signup)
                browser_case(browser,origin,landed,signup=signup,screenshot=os.getenv('LOGIN_SCREENSHOT') if not signup else None)
        finally:browser.close()
    print('4 browser scenarios passed. DB/providers mocked; final redirect verified against loopback HTTPS.')


if __name__=='__main__':main()
