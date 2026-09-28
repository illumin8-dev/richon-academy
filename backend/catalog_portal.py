"""Admin-only API for course programs, runs and weekly sessions."""
import logging
import os
from typing import Annotated
from fastapi import APIRouter,Depends,FastAPI,HTTPException,Query,Request,Response
from auth_core import Principal
from auth_http import require_admin,AuthSettings,_origin,_csrf,cookie_token
from portal import HEADERS
import catalog_models as model
import catalog_store as store

logger=logging.getLogger('richon.catalog')

def make_router(settings):
    router=APIRouter(prefix='/portal/api/admin/catalog')
    def permitted(request:Request,admin:Annotated[Principal,Depends(require_admin)]):
        _origin(request,settings)
        token=cookie_token(request)
        if token is None: raise HTTPException(401,'authentication_required',headers=HEADERS)
        _csrf(request,token)
        return admin
    def run(response,fn,*args):
        response.headers.update(HEADERS)
        try:return fn(*args)
        except store.Rejected as exc:
            raise HTTPException(exc.status,exc.code,headers=HEADERS) from None
        except Exception:
            logger.warning('catalog_store_unavailable')
            raise HTTPException(503,'catalog_store_unavailable',headers=HEADERS) from None

    @router.get('/programs')
    def programs(response:Response,admin:Annotated[Principal,Depends(require_admin)],
                 include_archived:bool=False):
        return run(response,store.programs,include_archived)

    @router.get('/runs')
    def runs(response:Response,admin:Annotated[Principal,Depends(require_admin)],
             program_id:str|None=None,include_archived:bool=False):
        if program_id:
            try:model.uuid_text(program_id)
            except Exception: raise HTTPException(422,'invalid_request',headers=HEADERS) from None
        return run(response,store.runs,program_id,include_archived)

    @router.get('/runs/{run_id}/sessions')
    def sessions(run_id:str,response:Response,admin:Annotated[Principal,Depends(require_admin)],
                 include_archived:bool=False):
        try:model.uuid_text(run_id)
        except Exception: raise HTTPException(422,'invalid_request',headers=HEADERS) from None
        return run(response,store.sessions,run_id,include_archived)

    @router.post('/programs')
    def create_program(body:model.ProgramCreate,request:Request,response:Response,
                       admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'program.create',body)

    @router.post('/programs/update')
    def update_program(body:model.ProgramUpdate,request:Request,response:Response,
                       admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'program.update',body)

    @router.post('/runs')
    def create_run(body:model.RunCreate,request:Request,response:Response,
                   admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'run.create',body)

    @router.post('/runs/update')
    def update_run(body:model.RunUpdate,request:Request,response:Response,
                   admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'run.update',body)

    @router.post('/sessions')
    def create_session(body:model.SessionCreate,request:Request,response:Response,
                       admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'session.create',body)

    @router.post('/sessions/update')
    def update_session(body:model.SessionUpdate,request:Request,response:Response,
                       admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'session.update',body)
    return router

def install_if_enabled(app:FastAPI):
    if os.getenv('RICHON_CATALOG_ENABLED','false')!='true':return False
    if os.getenv('RICHON_AUTH_ENABLED')!='true' or os.getenv('RICHON_PORTAL_ENABLED')!='true':
        raise ValueError('catalog_requires_private_portal')
    origins=frozenset(x.strip() for x in os.getenv('RICHON_AUTH_ALLOWED_ORIGINS','').split(',') if x.strip())
    app.include_router(make_router(AuthSettings(origins)))
    return True
