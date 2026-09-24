"""Native Chromium forms, intercepted synthetic application only; no cloud or DB."""
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from uuid import uuid4
import os
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_ui_fixture import shared_asset
from playwright.sync_api import sync_playwright
import auth_core as core
import oauth_http as h
import oauth_store as store
import member_profile_store as profiles
from test_member_profile import cfg

ORIGIN = 'https://localhost'


def run_case(browser, width, consent=None, provider='kakao'):
    app=FastAPI();app.include_router(h.make_router(replace(cfg(), origin=ORIGIN)))
    context=browser.new_context(viewport={'width':width,'height':900},service_workers='block')
    captured=[]
    signup=consent is not None
    if signup:
        context.add_cookies([{'name':name,'value':value,'url':ORIGIN,'secure':True,'httpOnly':True,'sameSite':'Lax'}
                            for name,value in [(h.BROWSER,'B'*43),(h.TICKET,'T'*43)]])
    def intercept(route):
        if shared_asset(route, ORIGIN): return
        request=route.request;url=urlsplit(request.url)
        assert url.scheme+'://'+url.netloc == ORIGIN, 'Unexpected network blocked'
        with TestClient(app,base_url=ORIGIN) as client:
            response=client.request(request.method,request.url,headers=request.all_headers(),
                content=request.post_data_buffer,follow_redirects=False)
        if request.method=='POST':
            captured.append((url.path,response.status_code,request.all_headers().get('origin')))
            assert response.status_code==303
            route.fulfill(status=200,content_type='text/html',body='<h1>TEST COMPLETE</h1>')
        else:
            route.fulfill(status=response.status_code,headers=dict(response.headers),body=response.content)
    context.route('**/*',intercept)
    identity=core.VerifiedIdentity('naver','test-naver','synthetic-uid','회원')
    saved=Mock(return_value=(uuid4(),'/portal/mypage'))
    with patch.object(store,'pending',return_value=(identity,'/portal/mypage')), \
         patch.object(store,'begin',return_value='S'*43), \
         patch.object(profiles,'finish',saved), \
         patch.object(h,'complete',side_effect=lambda mid,req,target:h.redirect(target)):
        page=context.new_page();page.goto(ORIGIN+('/auth/signup' if signup else '/auth/login'))
        assert not page.locator('input[type=password]').count()
        assert not page.locator('input[type=checkbox]:checked').count()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        if signup:
            page.get_by_role('button',name='동의하고 가입 완료').click()
            assert not captured
            page.locator('[name=name]').fill('가상 회원')
            page.locator('[name=phone]').fill('010-1234-5678')
            page.locator('[name=email]').fill('synthetic@example.invalid')
            page.locator('[name=age_range]').select_option('30-39')
            page.locator('[name=gender]').select_option('female')
            for key in ('over14','terms','privacy'):
                page.locator(f'[name={key}]').check()
            if consent:
                page.locator('[name=consultation]').check()
            page.locator('.collection-notice').evaluate('(el) => el.open=true')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            page.get_by_role('button',name='동의하고 가입 완료').click()
            page.get_by_role('heading',name='TEST COMPLETE').wait_for()
            record=saved.call_args.args[-1]
            assert record.consultation_consent is consent
            assert record.age_range == ('30-39' if consent else None)
            assert record.gender == ('female' if consent else None)
        else:
            label='카카오' if provider=='kakao' else '네이버'
            button=page.get_by_role('button',name=label+'로 로그인')
            button.click();assert not captured
            page.locator('[name=over14]').check();button.click()
            page.get_by_role('heading',name='TEST COMPLETE').wait_for()
        assert len(captured)==1 and captured[0][1:]==(303,ORIGIN)
    context.close()


def main():
    with sync_playwright() as p:
        options={'headless':True}
        if os.getenv('RICHON_TEST_CHROMIUM'):
            options['executable_path']=os.environ['RICHON_TEST_CHROMIUM']
        browser=p.chromium.launch(**options)
        try:
            for provider in ('kakao','naver'):
                run_case(browser,390,provider=provider)
            for width in (320,390,1280):
                for consent in (False,True):
                    run_case(browser,width,consent)
        finally:
            browser.close()
    print('PASS: 8 synthetic Chromium cases / age-before-provider, required fields, optional consent, same-origin POST, mobile width.')


if __name__=='__main__':
    main()
