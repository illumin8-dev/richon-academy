"""Feature-gated canonical course/run/session/enrollment portal."""
import logging
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter,Depends,FastAPI,HTTPException,Query,Request,Response
from fastapi.responses import FileResponse

from auth_core import Principal
from auth_http import require_member,require_admin,AuthSettings,_origin,_csrf,cookie_token
from portal import PAGE_HEADERS,HEADERS,PageQuery
import course_domain_models as model
import course_domain_store as store

logger=logging.getLogger('richon.course_domain')
STATIC=Path(__file__).parent/'portal_static'


def make_router(settings:AuthSettings):
    router=APIRouter(prefix='/portal/api')

    def read(response,fn,*args):
        response.headers.update(HEADERS)
        try:return fn(*args)
        except Exception:
            logger.warning('course_domain_store_unavailable')
            raise HTTPException(503,'course_domain_store_unavailable',headers=HEADERS) from None

    def permitted(request:Request,admin:Annotated[Principal,Depends(require_admin)]):
        _origin(request,settings)
        token=cookie_token(request)
        if token is None:raise HTTPException(401,'authentication_required',headers=HEADERS)
        _csrf(request,token)
        return admin

    def write(response,admin,operation,body):
        response.headers.update(HEADERS)
        try:return store.mutate(admin.member_id,operation,body)
        except store.Rejected as exc:
            raise HTTPException(exc.status,exc.code,headers=HEADERS) from None
        except Exception:
            logger.warning('course_domain_store_unavailable')
            raise HTTPException(503,'course_domain_store_unavailable',headers=HEADERS) from None

    @router.get('/me/courses')
    def my_courses(response:Response,member:Annotated[Principal,Depends(require_member)],
                   params:Annotated[PageQuery,Query()]):
        return read(response,store.my_courses,member.member_id,params.limit,params.offset)

    @router.get('/admin/learning/programs')
    def programs(response:Response,admin:Annotated[Principal,Depends(require_admin)],
                 limit:int=Query(100,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),
                 include_archived:bool=False):
        return read(response,store.programs,limit,offset,include_archived)

    @router.get('/admin/learning/runs')
    def runs(response:Response,admin:Annotated[Principal,Depends(require_admin)],
             program_id:str|None=Query(default=None,max_length=64),limit:int=Query(100,ge=1,le=100),
             offset:int=Query(0,ge=0,le=10000),include_archived:bool=False):
        return read(response,store.runs,program_id,limit,offset,include_archived)

    @router.get('/admin/learning/sessions')
    def sessions(response:Response,admin:Annotated[Principal,Depends(require_admin)],
                 run_id:UUID,include_cancelled:bool=False):
        return read(response,store.sessions,run_id,include_cancelled)

    @router.get('/admin/learning/enrollments')
    def enrollments(response:Response,admin:Annotated[Principal,Depends(require_admin)],
                    run_id:UUID|None=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=10000)):
        return read(response,store.enrollments,run_id,limit,offset)

    @router.get('/admin/learning/targets')
    def targets(response:Response,admin:Annotated[Principal,Depends(require_admin)],
                q:str=Query(default='',max_length=200),limit:int=Query(20,ge=1,le=50)):
        return read(response,store.targets,q.strip(),limit)

    @router.post('/admin/learning/programs')
    def create_program(body:model.ProgramCreate,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'program.create',body)

    @router.post('/admin/learning/programs/update')
    def update_program(body:model.ProgramUpdate,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'program.update',body)

    @router.post('/admin/learning/runs')
    def create_run(body:model.RunCreate,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'run.create',body)

    @router.post('/admin/learning/runs/update')
    def update_run(body:model.RunUpdate,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'run.update',body)

    @router.post('/admin/learning/sessions')
    def create_session(body:model.SessionCreate,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'session.create',body)

    @router.post('/admin/learning/sessions/update')
    def update_session(body:model.SessionUpdate,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'session.update',body)

    @router.post('/admin/learning/enrollments')
    def grant(body:model.EnrollmentGrant,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.grant',body)

    @router.post('/admin/learning/enrollments/cancel')
    def cancel(body:model.EnrollmentCancel,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.cancel',body)

    return router


def install_if_enabled(app:FastAPI):
    if os.getenv('RICHON_COURSE_DOMAIN_ENABLED','false')!='true':return False
    if (os.getenv('RICHON_AUTH_ENABLED')!='true' or os.getenv('RICHON_PORTAL_ENABLED')!='true'
        or not any(getattr(r,'path',None)=='/portal/api/admin/summary' for r in app.routes)):
        raise ValueError('course_domain_requires_private_portal')
    origins=frozenset(x.strip() for x in os.getenv('RICHON_AUTH_ALLOWED_ORIGINS','').split(',') if x.strip())
    app.include_router(make_router(AuthSettings(origins)))

    @app.get('/portal/courses',include_in_schema=False)
    def page():return FileResponse(STATIC/'courses.html',headers=PAGE_HEADERS)

    @app.get('/portal/course-assets/{asset}',include_in_schema=False)
    def asset(asset:str):
        if asset not in {'courses.css','courses.js'}:raise HTTPException(404,'not_found',headers=HEADERS)
        return FileResponse(STATIC/asset,headers=HEADERS)
    return True
