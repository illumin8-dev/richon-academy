"""Feature-gated admin CRUD for manual legacy records. No mock login routes."""
import logging
import os
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter,Depends,FastAPI,HTTPException,Request,Response
from fastapi.responses import FileResponse
from auth_core import Principal
from auth_http import require_admin,AuthSettings,_origin,_csrf,cookie_token
from portal import PAGE_HEADERS,HEADERS
import monthly_store
import manual_models as model
import manual_store as store

logger=logging.getLogger('richon.manual')
STATIC=Path(__file__).parent/'portal_static'

def make_router(settings):
    router=APIRouter(prefix='/portal/api/admin/manual')
    def permitted(request:Request,admin:Annotated[Principal,Depends(require_admin)]):
        _origin(request,settings)
        token=cookie_token(request)
        if token is None: raise HTTPException(401,'authentication_required',headers=HEADERS)
        _csrf(request,token)
        return admin
    def run(response, fn, *args):
        response.headers.update(HEADERS)
        try: return fn(*args)
        except store.Rejected as exc:
            raise HTTPException(exc.status,exc.code,headers=HEADERS) from None
        except Exception:
            logger.warning('manual_store_unavailable')
            raise HTTPException(503,'manual_store_unavailable',headers=HEADERS) from None
    @router.get('/options')
    def options(response:Response,admin:Annotated[Principal,Depends(require_admin)]):
        return run(response,monthly_store.options)
    @router.post('/search')
    def search(body:model.Search,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.search,admin.member_id,body)
    @router.post('/read')
    def read(body:model.Read,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.detail,admin.member_id,body.enrollment_id)
    @router.post('/create')
    def create(body:model.Create,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'create',body)
    @router.post('/profile')
    def profile(body:model.Update,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'profile',body)
    @router.post('/terms/add')
    def add(body:model.AddTerm,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'term.add',body)
    @router.post('/terms/edit')
    def edit(body:model.EditTerm,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'term.edit',body)
    @router.post('/archive')
    def archive(body:model.Archive,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'archive',body)
    @router.post('/courses')
    def course(body:model.Course,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return run(response,store.mutate,admin.member_id,'course.create',body)
    return router


def install_if_enabled(app:FastAPI):
    if os.getenv('RICHON_MANUAL_ENABLED','false')!='true': return False
    if (os.getenv('RICHON_AUTH_ENABLED')!='true' or os.getenv('RICHON_PORTAL_ENABLED')!='true'
        or os.getenv('RICHON_MONTHLY_ENABLED')!='true'
        or not any(getattr(r,'path',None)=='/portal/enrollments' for r in app.routes)):
        raise ValueError('manual_requires_private_monthly_portal')
    origins=frozenset(x.strip() for x in os.getenv('RICHON_AUTH_ALLOWED_ORIGINS','').split(',') if x.strip())
    app.include_router(make_router(AuthSettings(origins)))
    @app.get('/portal/manual',include_in_schema=False)
    def page(): return FileResponse(STATIC/'manual.html',headers=PAGE_HEADERS)
    @app.get('/portal/manual-assets/{asset}',include_in_schema=False)
    def asset(asset:str):
        if asset not in {'manual.css','manual.js'}: raise HTTPException(404,'not_found',headers=HEADERS)
        return FileResponse(STATIC/asset,headers=HEADERS)
    return True
