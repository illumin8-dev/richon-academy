"""Feature-gated own-account mutations. Default OFF.

Profile values never identify an account. Linking uses an existing member
session + a new provider proof + a separate confirmation. Provider unlinking
uses a fresh provider OAuth proof and revokes the provider token before the
local identity is removed.
"""
import logging
import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict

import account_store as store
import auth_core as core
import auth_http as auth
import member_profile
import marketing_consent as marketing
import oauth_http
import oauth_providers as providers

HEADERS={'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
         'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY'}
logger=logging.getLogger('richon.account')


class ProfileUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    name:str
    phone:str
    email:str
    age_range:str|None=None
    gender:str|None=None
    consultation_consent:bool=False

    def registration(self):
        return member_profile.Registration(
            self.name,self.phone,self.email,self.age_range,self.gender,
            self.consultation_consent,True,False)


class MarketingUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    consent:bool


class WithdrawBody(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    confirm:str


def denied(status,detail):
    return HTTPException(status,detail,headers=HEADERS)


def settings():
    return providers.Settings.from_env()


def csrf_request(request,cfg):
    auth._origin(request,auth.AuthSettings(frozenset({cfg.origin})))
    token=auth.cookie_token(request)
    if token is None:
        raise denied(401,'authentication_required')
    auth._csrf(request,token)
    return token


def form_csrf(request,data,cfg):
    auth._origin(request,auth.AuthSettings(frozenset({cfg.origin})))
    token=auth.cookie_token(request)
    if token is None or not core.valid_csrf(token,data.get('csrf')):
        raise denied(403,'csrf_failed')
    return token


def require_fresh(token,member):
    try:
        if not store.recent_session(token,member.member_id):
            raise denied(409,'reauth_required')
    except HTTPException:
        raise
    except Exception:
        logger.warning('account_store_unavailable')
        raise denied(503,'account_store_unavailable') from None


def map_error(error):
    if isinstance(error,store.AlreadyLinked): return denied(409,'already_linked')
    if isinstance(error,store.ProviderNotLinked): return denied(409,'provider_not_linked')
    if isinstance(error,store.IdentityInUse): return denied(409,'identity_already_in_use')
    if isinstance(error,store.LastLoginMethod): return denied(409,'last_login_method')
    if isinstance(error,store.ProfileUnavailable): return denied(409,'profile_unavailable')
    if isinstance(error,store.AdminWithdrawalNotAllowed): return denied(409,'admin_withdrawal_not_allowed')
    if isinstance(error,store.WithdrawalNotPrepared): return denied(409,'withdrawal_not_prepared')
    if isinstance(error,store.WithdrawalInProgress): return denied(409,'withdrawal_in_progress')
    if isinstance(error,store.LifecycleNotReady): return denied(503,'withdrawal_cleanup_not_ready')
    if isinstance(error,core.MemberUnavailable): return denied(401,'authentication_required')
    if isinstance(error,(store.AccountActionRejected,member_profile.InvalidProfile)):
        return denied(422,'invalid_account_action')
    logger.warning('account_store_unavailable')
    return denied(503,'account_store_unavailable')


def clear_ephemeral(response):
    for name in (oauth_http.BROWSER,oauth_http.LINK):
        response.delete_cookie(name,path='/',secure=True,httponly=True,samesite='lax')


def make_router(cfg):
    router=APIRouter(prefix='/portal/api/me')

    @router.get('/security')
    def security(request:Request,
                 member:Annotated[core.Principal,Depends(auth.require_member)]):
        token=auth.cookie_token(request)
        try:
            return {
                'fresh_auth':bool(token and store.recent_session(token,member.member_id)),
                'provider_unlink_failed':store.unlink_failure_pending(member.member_id),
            }
        except Exception:
            logger.warning('account_store_unavailable')
            raise denied(503,'account_store_unavailable') from None

    @router.post('/profile',status_code=204)
    def update_profile(request:Request,body:Annotated[ProfileUpdate,Body()],
                       member:Annotated[core.Principal,Depends(auth.require_member)]):
        csrf_request(request,cfg)
        try:
            store.update_profile(member.member_id,body.registration())
        except Exception as error:
            raise map_error(error)
        return Response(status_code=204,headers=HEADERS)

    @router.post('/marketing')
    def update_marketing(request:Request,body:Annotated[MarketingUpdate,Body()],
                         member:Annotated[core.Principal,Depends(auth.require_member)]):
        if not marketing.enabled():
            raise denied(404,'not_found')
        csrf_request(request,cfg)
        try:
            store.set_marketing_consent(member.member_id,body.consent)
        except Exception as error:
            raise map_error(error)
        return JSONResponse({
            'consent':body.consent,
            'channels':list(marketing.CHANNELS) if body.consent else [],
        },headers=HEADERS)

    async def start(request,member,action,*,fresh):
        data=await oauth_http.form(request,{'csrf','provider'})
        token=form_csrf(request,data,cfg)
        if fresh:
            require_fresh(token,member)
        provider=data.get('provider')
        try:
            browser=oauth_http.cookie(request,oauth_http.BROWSER,required=False) or secrets.token_urlsafe(32)
            state=store.begin_action(cfg,member.member_id,provider,action,browser)
            response=RedirectResponse(providers.authorization_url(cfg,provider,state,browser,reauthenticate=True),
                                      status_code=303,headers=HEADERS)
            oauth_http.set_temporary(response,oauth_http.BROWSER,browser)
            return response
        except HTTPException:
            raise
        except Exception as error:
            raise map_error(error)

    @router.post('/logins/link/start')
    async def start_link(request:Request,
                         member:Annotated[core.Principal,Depends(auth.require_member)]):
        return await start(request,member,'link',fresh=True)

    @router.post('/reauth/start')
    async def start_reauth(request:Request,
                           member:Annotated[core.Principal,Depends(auth.require_member)]):
        return await start(request,member,'reauth',fresh=False)

    @router.post('/logins/unlink/start')
    async def start_unlink(request:Request,
                           member:Annotated[core.Principal,Depends(auth.require_member)]):
        return await start(request,member,'unlink',fresh=True)

    @router.post('/withdraw/provider/start')
    async def start_withdraw_provider(request:Request,
                                      member:Annotated[core.Principal,Depends(auth.require_member)]):
        return await start(request,member,'withdraw',fresh=False)

    @router.get('/logins/link/pending')
    def link_pending(request:Request,
                     member:Annotated[core.Principal,Depends(auth.require_member)]):
        try:
            ticket=oauth_http.cookie(request,oauth_http.LINK,required=False)
            browser=oauth_http.cookie(request,oauth_http.BROWSER,required=False)
            if not ticket or not browser:
                return Response(status_code=204,headers=HEADERS)
            provider=store.pending_link(cfg,ticket,browser,member.member_id)
            if provider is None:
                response=Response(status_code=204,headers=HEADERS)
                clear_ephemeral(response)
                return response
            return JSONResponse({'provider':provider},headers=HEADERS)
        except Exception as error:
            raise map_error(error)

    @router.post('/logins/link/confirm')
    def confirm_link(request:Request,
                     member:Annotated[core.Principal,Depends(auth.require_member)]):
        csrf_request(request,cfg)
        try:
            ticket=oauth_http.cookie(request,oauth_http.LINK)
            browser=oauth_http.cookie(request,oauth_http.BROWSER)
            values=store.confirm_link(cfg,ticket,browser,member.member_id)
            response=JSONResponse({'providers':values},headers=HEADERS)
            clear_ephemeral(response)
            return response
        except Exception as error:
            raise map_error(error)

    @router.post('/logins/link/cancel',status_code=204)
    def cancel_link(request:Request,
                    member:Annotated[core.Principal,Depends(auth.require_member)]):
        csrf_request(request,cfg)
        try:
            ticket=oauth_http.cookie(request,oauth_http.LINK,required=False)
            browser=oauth_http.cookie(request,oauth_http.BROWSER,required=False)
            if ticket and browser:
                store.cancel_link(ticket,browser,member.member_id)
            response=Response(status_code=204,headers=HEADERS)
            clear_ephemeral(response)
            return response
        except Exception as error:
            raise map_error(error)

    @router.post('/withdraw/prepare')
    def prepare_withdraw(request:Request,body:Annotated[WithdrawBody,Body()],
                         member:Annotated[core.Principal,Depends(auth.require_member)]):
        token=csrf_request(request,cfg)
        require_fresh(token,member)
        if body.confirm!='회원탈퇴':
            raise denied(422,'withdrawal_confirmation_required')
        try:
            store.prepare_withdrawal(member.member_id)
            return {'providers':store.withdrawal_status(member.member_id,cfg) or []}
        except Exception as error:
            raise map_error(error)

    @router.get('/withdraw/status')
    def withdraw_status(member:Annotated[core.Principal,Depends(auth.require_member)]):
        try:
            values=store.withdrawal_status(member.member_id,cfg)
            if values is None:
                return Response(status_code=204,headers=HEADERS)
            return JSONResponse({'providers':values},headers=HEADERS)
        except Exception as error:
            raise map_error(error)

    @router.post('/withdraw/cancel',status_code=204)
    def cancel_withdraw(request:Request,
                        member:Annotated[core.Principal,Depends(auth.require_member)]):
        csrf_request(request,cfg)
        try:
            store.cancel_withdrawal(member.member_id)
            return Response(status_code=204,headers=HEADERS)
        except Exception as error:
            raise map_error(error)

    return router


def install_if_enabled(app:FastAPI):
    if os.getenv('RICHON_ACCOUNT_ENABLED','false')!='true':
        return False
    if (os.getenv('RICHON_AUTH_ENABLED')!='true' or os.getenv('RICHON_OAUTH_ENABLED')!='true'
            or os.getenv('RICHON_PORTAL_ENABLED')!='true'
            or not any(getattr(r,'path',None)=='/portal/api/me' for r in app.routes)):
        raise ValueError('account_requires_member_portal')
    cfg=settings()
    if not member_profile.enabled(cfg.terms_version,cfg.privacy_version):
        raise ValueError('account_requires_member_profile_policy')
    app.include_router(make_router(cfg))
    return True
