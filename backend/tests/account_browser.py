"""Synthetic Chromium contract for the shared member shell; no live provider or database."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4
import json
import os
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]

from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect

import auth_core as core
import auth_http as auth
import oauth_http as oauth
import oauth_store
import portal
import portal_store
from portal_entry import EdgeBoundary
from shared_ui_fixture import shared_asset
from test_oauth import settings, ORIGIN

KEY='E'*43
TOKEN='X'*43

def make_app():
    cfg=replace(settings(),terms_url=ORIGIN+'/terms.html',privacy_url=ORIGIN+'/privacy.html')
    app=FastAPI()
    app.include_router(auth.make_router(auth.AuthSettings(frozenset({ORIGIN}))))
    app.include_router(oauth.make_router(cfg))
    portal.install_if_enabled(app)
    app.add_middleware(EdgeBoundary,enabled=True,secret=KEY)
    return app

def main():
    os.environ['RICHON_AUTH_ENABLED']='true'
    os.environ['RICHON_PORTAL_ENABLED']='true'
    os.environ['RICHON_ACCOUNT_ENABLED']='true'
    principal=core.Principal(uuid4(),'테스트 회원','member',datetime.now(timezone.utc))
    profile={
        'member_id':principal.member_id,'display_name':'회원','role':'member',
        'created_at':datetime.now(timezone.utc),'providers':['kakao','naver'],
        'linked_order_count':0,
        'registration':{
            'name':'합성 회원','phone':'01012345678','email':'synthetic@example.invalid',
            'age_range':'30-39','gender':'female','consultation_consent':True,
            'consented_at':datetime.now(timezone.utc),
        },
    }
    orders={'items':[],'limit':20,'offset':0,'has_more':False}
    app=make_app()
    with patch.object(core,'resolve_session',return_value=principal), patch.object(portal_store,'profile',return_value=profile), patch.object(portal_store,'own_orders',return_value=orders), patch.object(oauth_store,'begin',return_value='S'*43), sync_playwright() as p:
        kwargs={'headless':True}
        if os.getenv('RICHON_TEST_CHROMIUM'): kwargs['executable_path']=os.environ['RICHON_TEST_CHROMIUM']
        browser=p.chromium.launch(**kwargs)
        context=browser.new_context(viewport={'width':1280,'height':900},service_workers='block')
        context.add_cookies([{'name':auth.COOKIE,'value':TOKEN,'url':ORIGIN,'secure':True,'httpOnly':True,'sameSite':'Lax'}])
        def route(reqroute):
            if shared_asset(reqroute,ORIGIN): return
            req=reqroute.request
            url=urlsplit(req.url)
            if url.netloc=='cdn.jsdelivr.net':
                reqroute.fulfill(status=200,content_type='text/css',body='')
                return
            if req.method=='GET' and url.netloc in {'kauth.kakao.com','nid.naver.com'}:
                reqroute.fulfill(status=200,content_type='text/html',body='<h1>PROVIDER</h1>')
                return
            assert url.scheme+'://'+url.netloc==ORIGIN
            if url.path=='/portal/api/me/security':
                reqroute.fulfill(status=200,content_type='application/json',body=json.dumps({'fresh_auth':True,'provider_unlink_failed':False}));return
            if url.path in {'/portal/api/me/logins/link/pending','/portal/api/me/withdraw/status'}:
                reqroute.fulfill(status=204,body='');return
            if url.path=='/portal/api/me/profile' and req.method=='POST':
                reqroute.fulfill(status=204,body='');return
            headers=dict(req.all_headers());headers['X-Richon-Edge-Key']=KEY
            with TestClient(app,base_url=ORIGIN) as client:
                response=client.request(req.method,req.url,headers=headers,content=req.post_data_buffer,follow_redirects=False)
            reqroute.fulfill(status=response.status_code,headers=dict(response.headers),body=response.content)
        context.route('**/*',route)
        page=context.new_page()
        for width in (320,390,1280):
            page.set_viewport_size({'width':width,'height':900})
            page.goto(ORIGIN+'/portal/mypage')
            expect(page.get_by_role('heading',name='마이페이지')).to_be_visible()
            expect(page.locator('.sidebar')).to_have_count(0)
            expect(page.locator('#edit-profile')).to_be_visible()
            expect(page.locator('#manage-logins')).to_be_visible()
            expect(page.locator('#withdraw-account')).to_be_visible()
            expect(page.locator('#withdraw-inquiry')).to_be_hidden()
            assert page.locator('#withdraw-account').evaluate('e=>getComputedStyle(e).fontSize')=='12px'
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.set_viewport_size({'width':1280,'height':900})
        page.goto(ORIGIN+'/portal/mypage')
        page.locator('#edit-profile').click()
        expect(page.locator('#profile-dialog')).to_be_visible()
        expect(page.locator('#edit-name')).to_have_value('합성 회원')
        expect(page.locator('#edit-age')).to_have_value('30-39')
        page.locator('[data-close-dialog]').first.click()
        page.locator('#manage-logins').click()
        expect(page.locator('#login-dialog')).to_be_visible()
        expect(page.locator('#login-connections .account-login-row')).to_have_count(2)
        expect(page.locator('#login-connections')).to_contain_text('카카오')
        expect(page.locator('#login-connections')).to_contain_text('네이버')
        page.keyboard.press('Escape')
        page.locator('#withdraw-account').click()
        expect(page.locator('#withdraw-dialog')).to_be_visible()
        expect(page.locator('#withdraw-dialog')).to_contain_text('환불')
        expect(page.locator('#withdraw-dialog')).to_contain_text('회원탈퇴')
        page.keyboard.press('Escape')
        context.clear_cookies()
        page.goto(ORIGIN+'/portal/mypage')
        expect(page.locator('#gate-login')).to_be_visible()
        page.locator('#gate-login').click()
        expect(page.locator('#richon-login-dialog')).to_be_visible()
        expect(page.locator('#richon-login-dialog .provider-login')).to_have_count(2)
        assert '계정으로 계속' not in page.locator('#richon-login-dialog').inner_text()
        page.keyboard.press('Escape')
        expect(page.locator('#richon-login-dialog')).to_be_hidden()
        expect(page.locator('#gate-login')).to_be_focused()
        page.locator('#gate-login').click()
        page.locator('#richon-login-dialog .kakao-login').click()
        expect(page.get_by_role('heading',name='PROVIDER')).to_be_visible()
        context.close();browser.close()
    print('PASS: shared member chrome, responsive shell, account edit/link/withdraw dialogs, quiet withdrawal action and same-page provider selector; synthetic only')

if __name__=='__main__':
    main()
