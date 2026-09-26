"""Disabled-by-default social-login HTTP flow; no provider credentials in HTML."""
import html
import hmac
import hashlib
import logging
import os
import re
import secrets
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlencode
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
import auth_core as core
import auth_http as auth
import account_store as accounts
import oauth_store as store
import oauth_providers as providers
import member_profile
import member_profile_store
import marketing_consent as marketing
import signup_views

BROWSER='__Host-richon-oauth'
TICKET='__Host-richon-signup'
LINK='__Host-richon-link'
HEADERS={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY'}
CSP="default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css; font-src 'self' https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self' https://kauth.kakao.com https://nid.naver.com"
logger=logging.getLogger('richon.oauth')


def cookie(request,name,required=True):
    found=[]
    for h in request.headers.getlist('cookie'):
        for part in h.split(';'):
            key,sep,val=part.strip().partition('=')
            if key==name and sep: found.append(val)
    if not found and not required: return None
    if len(found)!=1: raise store.InvalidFlow()
    try: core.token_digest(found[0])
    except core.AuthenticationRequired: raise store.InvalidFlow() from None
    return found[0]


def proof(browser,ticket=None):
    message=b'richon/oauth-form/v1' if ticket is None else ('richon/signup-form/v1/'+core.token_digest(ticket)).encode()
    return hmac.new(browser.encode(),message,hashlib.sha256).hexdigest()


def set_temporary(response,name,value):
    response.set_cookie(name,value,max_age=600,secure=True,httponly=True,samesite='lax',path='/')


def redirect(target):
    return RedirectResponse(target,status_code=303,headers=HEADERS)


def failed(return_to='/'):
    logger.warning('oauth_flow_not_completed')
    target = '/auth/login?error=login_failed'
    if return_to in providers.RETURNS and return_to != '/':
        target += '&' + urlencode({'return_to': return_to})
    return redirect(target)


def page(title,body):
    content='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>리치온아카데미 / '''+html.escape(title)+'''</title><style>body{font:16px/1.7 var(--site-font);margin:0;background:#fff7ed;color:#30241c}main{max-width:440px;margin:8vh auto;padding:32px;box-sizing:border-box;width:calc(100% - 32px);background:white;border-radius:16px}h1{font-size:26px}form{display:grid;gap:16px}button{padding:13px;font:inherit;border:1px solid #e7d6c5;border-radius:8px;cursor:pointer}p{color:#706054}label{display:block}a{color:#c44916}input{accent-color:#c44916}.collection-notice{font-size:13px;margin:16px 0}.collection-notice summary{cursor:pointer}.collection-notice table{width:100%;border-collapse:collapse;table-layout:fixed}.collection-notice td,.collection-notice th{padding:8px 4px;text-align:left;border-bottom:1px solid #eee;overflow-wrap:anywhere}.collection-notice caption{margin-top:12px}input:not([type=checkbox]):not([type=hidden]),select{box-sizing:border-box;width:100%;padding:10px;font:inherit;min-width:0}fieldset{min-width:0;border:1px solid #e7d6c5;border-radius:8px}fieldset p{font-size:13px}.provider-login{border:0;padding:0;width:100%;height:48px;min-height:48px;display:flex;align-items:center;justify-content:center;overflow:hidden;line-height:0;border-radius:12px}.provider-login img{display:block;max-width:none;flex-shrink:0}.provider-login:focus-visible{outline:3px solid #30241c;outline-offset:4px}.kakao-login{background:#fee500}.kakao-login img{width:448px;height:46px}.naver-login{background:#03a94d}.naver-login img{width:368px;height:48px}</style></head><body><main><p>RICHON ACADEMY</p><h1>'''+html.escape(title)+'''</h1>'''+body+'''</main></body></html>'''
    static = Path(__file__).parent / 'portal_static'
    header = (static / 'site-header.html').read_text()
    footer = (static / 'site-footer.html').read_text()
    assets = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" crossorigin referrerpolicy="no-referrer"><link rel="stylesheet" href="/portal/assets/site.css"><script src="/portal/assets/site.js"></script><script defer src="/portal/assets/signup.js"></script>'
    content = content.replace('</head>', assets + '</head>', 1)
    content = content.replace('<body><main><p>RICHON ACADEMY</p>', '<body class="richon-page auth-page">' + header + '<main>', 1)
    content = content.replace('</main></body>', '</main>' + footer + '</body>', 1)
    # Native form POSTs need a non-null same-origin Origin. Cross-site referrers
    # remain suppressed; callback/redirect/error responses keep no-referrer.
    return HTMLResponse(content,headers={**HEADERS,'Referrer-Policy':'same-origin','Content-Security-Policy':CSP})


async def form(request,allowed):
    if request.headers.get('content-type','').split(';')[0].strip()!='application/x-www-form-urlencoded':
        raise HTTPException(415,'invalid_form',headers=HEADERS)
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>4096: raise HTTPException(413,'invalid_form',headers=HEADERS)
    try: pairs=parse_qsl(raw.decode('utf-8'),keep_blank_values=True,strict_parsing=True,max_num_fields=16)
    except (ValueError,UnicodeError): raise HTTPException(422,'invalid_form',headers=HEADERS) from None
    if len(dict(pairs))!=len(pairs) or any(k not in allowed for k,v in pairs):
        raise HTTPException(422,'invalid_form',headers=HEADERS)
    return dict(pairs)


def check_post(request,data,settings,*,signup=False):
    auth._origin(request,auth.AuthSettings(frozenset({settings.origin})))
    try:
        browser=cookie(request,BROWSER)
        ticket=cookie(request,TICKET) if signup else None
    except store.InvalidFlow: raise HTTPException(403,'invalid_login_flow',headers=HEADERS) from None
    supplied=data.get('csrf','')
    if not re.fullmatch(r'[a-f0-9]{64}',supplied) or not hmac.compare_digest(proof(browser,ticket),supplied):
        raise HTTPException(403,'invalid_login_flow',headers=HEADERS)
    return browser


def complete(member_id,request,return_to):
    if return_to not in providers.RETURNS: raise store.InvalidFlow()
    old=auth.cookie_token(request)
    session=core.issue_session(member_id,replace_token=old)
    response=redirect(return_to)
    auth.set_session_cookie(response,session)
    response.delete_cookie(TICKET,path='/',secure=True,httponly=True,samesite='lax')
    response.delete_cookie(BROWSER,path='/',secure=True,httponly=True,samesite='lax')
    return response


def login_return(request, settings):
    """Explicit allowlisted target wins. Referer is only a navigation hint.

    Never accept an external target or infer identity/CSRF validity from it.
    Query strings/fragments and entered form data are intentionally not retained.
    """
    values = request.query_params.getlist('return_to')
    if values:
        if len(values) != 1 or values[0] not in providers.RETURNS:
            raise HTTPException(422, 'invalid_return', headers=HEADERS)
        return values[0]
    refs = request.headers.getlist('referer')
    if len(refs) == 1 and len(refs[0]) <= 2048 and not re.search(r'[\x00-\x20\x7f\\]', refs[0]):
        try:
            previous = urlsplit(refs[0])
            if (not previous.username and not previous.password
                and previous.scheme + '://' + previous.netloc == settings.origin
                and previous.path in providers.RETURNS):
                return previous.path
        except ValueError:
            pass
    return '/'


def make_router(settings):
    router=APIRouter(prefix='/auth')
    collect_profile = member_profile.enabled(settings.terms_version, settings.privacy_version)
    account_enabled = os.getenv('RICHON_ACCOUNT_ENABLED','false') == 'true'

    @router.get('/assets/kakao-login.png',include_in_schema=False)
    def kakao_button():
        return FileResponse(Path(__file__).parent / 'portal_static' / 'kakao-login.png',
                            media_type='image/png', headers=HEADERS)

    @router.get('/assets/naver-login.png',include_in_schema=False)
    def naver_button():
        return FileResponse(Path(__file__).parent / 'portal_static' / 'naver-login.png',
                            media_type='image/png', headers=HEADERS)

    @router.get('/login',response_class=HTMLResponse)
    def login(request:Request):
        target=login_return(request,settings)
        try: browser=cookie(request,BROWSER,required=False) or secrets.token_urlsafe(32)
        except store.InvalidFlow: return page('다시 시작해 주세요','<p>로그인 쿠키가 올바르지 않습니다. 이 사이트의 쿠키를 지우고 다시 접속해 주세요.</p>')
        views = request.query_params.getlist('view')
        if views and views != ['modal']:
            raise HTTPException(422, 'invalid_login_view', headers=HEADERS)
        if views:
            # Browser-bound form proof only; never a session/provider token.
            response = JSONResponse({
                'csrf': proof(browser), 'return_to': target,
                'providers': [name for name in ('kakao','naver') if name in settings.providers],
                'collect_profile': collect_profile,
                'notice': signup_views.notice(settings) if collect_profile else None,
            }, headers=HEADERS)
            set_temporary(response, BROWSER, browser)
            return response
        body=''
        if request.query_params.get('error'): body+='<p role="alert">로그인을 완료하지 못했습니다. 다시 시도해 주세요.</p>'
        if collect_profile:
            body += signup_views.notice(settings)
            body += f'<form method="post" action="/auth/start"><input type="hidden" name="csrf" value="{proof(browser)}"><input type="hidden" name="return_to" value="{target}"><label><input type="checkbox" name="over14" value="yes" required> [필수] 만 14세 이상입니다.</label>'
        for name,label in [('kakao','카카오'),('naver','네이버')]:
            if name in settings.providers:
                # Keep official image bytes/ratios and readable symbol sizes.
                # Narrow buttons clip only empty side padding, never the marks.
                width, height = (896, 92) if name == 'kakao' else (1472, 192)
                button = (f'<button class="provider-login {name}-login" type="submit" aria-label="{label}로 로그인">'
                          f'<img src="/auth/assets/{name}-login.png" alt="{label} 로그인" width="{width}" height="{height}" referrerpolicy="no-referrer"></button>')
                if collect_profile:
                    body += button.replace('type="submit"', f'type="submit" name="provider" value="{name}"')
                else:
                    body+=f'<form method="post" action="/auth/start"><input type="hidden" name="csrf" value="{proof(browser)}"><input type="hidden" name="provider" value="{name}"><input type="hidden" name="return_to" value="{target}">{button}</form><br>'
        if collect_profile:
            body += '</form>'
        response=page('간편 로그인',body)
        set_temporary(response,BROWSER,browser)
        return response

    @router.post('/start')
    async def start(request:Request):
        data=await form(request,{'csrf','provider','return_to'} | ({'over14'} if collect_profile else set()))
        browser=check_post(request,data,settings)
        if collect_profile and data.get('over14') != 'yes':
            raise HTTPException(422, 'age_confirmation_required', headers=HEADERS)
        name=data.get('provider');target=data.get('return_to','/')
        if name not in settings.providers or target not in providers.RETURNS:
            raise HTTPException(422,'invalid_login_request',headers=HEADERS)
        try:
            state=await run_in_threadpool(store.begin,settings,name,browser,target)
            return redirect(providers.authorization_url(settings,name,state,browser))
        except Exception: return failed(target)

    @router.get('/{provider}/callback')
    def callback(provider:str,request:Request):
        target='/'
        account_attempt=None
        try:
            pairs=list(request.query_params.multi_items());q=dict(pairs)
            if (len(pairs)!=len(q) or len(str(request.url.query))>8192 or not set(q)<= {'state','code','error','error_description'}
                or provider not in settings.providers): raise store.InvalidFlow()
            browser=cookie(request,BROWSER);state=q.get('state','')
            core.token_digest(state)
            code=q.get('code')
            if not q.get('error') and (not isinstance(code,str) or not 1<=len(code)<=2048 or any(ord(char)<33 or ord(char)>126 for char in code)): raise store.InvalidFlow()
            if account_enabled:
                account_attempt=accounts.consume_action_attempt(settings,provider,state,browser)
            if account_attempt is not None:
                if q.get('error'):
                    response=redirect('/portal/mypage')
                    response.delete_cookie(BROWSER,path='/',secure=True,httponly=True,samesite='lax')
                    return response
                verified=providers.exchange_session(settings,provider,code,state,browser)
                identity=verified.identity
                action,member_id,ticket=accounts.finish_verified_action(
                    settings,account_attempt,identity,browser)
                if action=='reauth':
                    return complete(member_id,request,'/portal/mypage')
                if action=='link':
                    response=redirect('/portal/mypage')
                    set_temporary(response,LINK,ticket)
                    return response
                try:
                    providers.unlink_access(settings,verified)
                except providers.ProviderRejected:
                    try: accounts.record_unlink_failure(member_id,provider)
                    except Exception: logger.warning('provider_unlink_failure_record_unavailable')
                    response=redirect('/portal/mypage')
                    response.delete_cookie(BROWSER,path='/',secure=True,httponly=True,samesite='lax')
                    return response
                if action=='unlink':
                    accounts.complete_unlink(settings,member_id,identity)
                    return complete(member_id,request,'/portal/mypage')
                remaining=accounts.complete_withdraw_provider(settings,member_id,identity)
                if remaining:
                    response=redirect('/portal/mypage')
                    response.delete_cookie(BROWSER,path='/',secure=True,httponly=True,samesite='lax')
                    return response
                accounts.finalize_withdrawal(member_id)
                response=redirect('/')
                auth.clear_session_cookie(response)
                for name in (BROWSER,TICKET,LINK):
                    response.delete_cookie(name,path='/',secure=True,httponly=True,samesite='lax')
                return response
            target=store.consume_attempt(settings,provider,state,browser)
            if q.get('error'): return failed(target)
            identity=providers.exchange(settings,provider,code,state,browser)
            member_id=store.member_for(identity)
            if member_id is not None and (not collect_profile or member_profile_store.completed(member_id, settings)):
                return complete(member_id,request,target)
            ticket=store.stage_signup(settings,identity,browser,target)
            response=redirect('/auth/signup');set_temporary(response,TICKET,ticket)
            return response
        except Exception:
            if account_attempt is not None:
                response=redirect('/portal/mypage')
                response.delete_cookie(BROWSER,path='/',secure=True,httponly=True,samesite='lax')
                return response
            return failed(target)

    @router.get('/signup',response_class=HTMLResponse)
    def signup_page(request:Request):
        try:
            browser=cookie(request,BROWSER);ticket=cookie(request,TICKET)
            identity, _ = store.pending(settings,ticket,browser)
        except Exception: return failed()
        if collect_profile:
            suggested = '' if identity.display_name == '회원' else identity.display_name
            return page('회원가입 안내', signup_views.signup_form(settings, proof(browser,ticket), suggested))
        e=html.escape
        body=f'''<p>처음 방문하셨습니다. 아래 문서를 확인한 뒤 가입해 주세요.</p>
<form method="post" action="/auth/signup"><input type="hidden" name="csrf" value="{proof(browser,ticket)}">
<input type="hidden" name="terms_version" value="{e(settings.terms_version)}"><input type="hidden" name="privacy_version" value="{e(settings.privacy_version)}">
<label><input type="checkbox" name="terms" value="yes" required> [필수] <a href="{e(settings.terms_url)}" target="_blank" rel="noopener noreferrer">이용약관</a> 동의</label>
<label><input type="checkbox" name="privacy" value="yes" required> [필수] <a href="{e(settings.privacy_url)}" target="_blank" rel="noopener noreferrer">개인정보 수집·이용 안내</a> 동의</label>
<p>홍보 수신 동의나 기존 수강기록 연결은 자동으로 처리하지 않습니다.</p><button type="submit">동의하고 가입</button></form>'''
        return page('회원가입 안내',body)

    @router.post('/signup')
    async def signup(request:Request):
        data=await form(request,{'csrf','terms','privacy','terms_version','privacy_version'} | ({'name','phone','email','over14','consultation','age_range','gender'} | ({'marketing'} if marketing.enabled() else set()) if collect_profile else set()))
        browser=check_post(request,data,settings,signup=True)
        if (data.get('terms')!='yes' or data.get('privacy')!='yes' or data.get('terms_version')!=settings.terms_version
            or data.get('privacy_version')!=settings.privacy_version):
            raise HTTPException(422,'consent_required',headers=HEADERS)
        if collect_profile:
            try:
                registration = member_profile.Registration.from_form(data)
            except member_profile.InvalidProfile as error:
                raise HTTPException(422, str(error), headers=HEADERS) from None
            def save_profile():
                try:
                    member, target = member_profile_store.finish(settings, cookie(request,TICKET), browser, registration)
                    return complete(member, request, target)
                except Exception:
                    return failed()
            return await run_in_threadpool(save_profile)
        def finish():
            target='/'
            try:
                identity,target=store.pending(settings,cookie(request,TICKET),browser,consume=True)
                member=core.register_verified_identity(identity,core.SignupConsent(settings.terms_version,settings.privacy_version))
                return complete(member,request,target)
            except Exception:
                # Only a return target recovered from the validated signup
                # ticket may survive this error. Never read it from the POST.
                return failed(target)
        try: return await run_in_threadpool(finish)
        except Exception: return failed()
    return router


def install_if_enabled(app:FastAPI):
    if os.getenv('RICHON_OAUTH_ENABLED','false')!='true': return False
    if os.getenv('RICHON_AUTH_ENABLED')!='true' or not any(getattr(r,'path',None)=='/auth/me' for r in app.routes):
        raise ValueError('oauth_requires_auth')
    app.include_router(make_router(providers.Settings.from_env()))
    return True
