"""Feature-gated canonical course/run/session/enrollment portal."""
from datetime import datetime, timezone
import logging
import os
import re
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter,Depends,FastAPI,HTTPException,Query,Request,Response
from fastapi.responses import FileResponse

from auth_core import Principal
from auth_http import require_member,require_admin,AuthSettings,_origin,_csrf,cookie_token
from portal import UI_PAGE_HEADERS,HEADERS,PageQuery
import course_domain_models as model
import course_domain_store as store

logger=logging.getLogger('richon.course_domain')
STATIC=Path(__file__).parent/'portal_static'


SEOUL=ZoneInfo('Asia/Seoul')

def _month_parts(value):
    if value is None:
        now=datetime.now(SEOUL);year,month=now.year,now.month
    else:
        if not re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])',value):
            raise HTTPException(422,'invalid_month',headers=HEADERS)
        year,month=map(int,value.split('-'))
    def shifted(delta):
        n=year*12+(month-1)+delta
        return n//12,n%12+1
    def utc_first(delta):
        y,m=shifted(delta)
        return datetime(y,m,1,tzinfo=SEOUL).astimezone(timezone.utc)
    return f'{year:04d}-{month:02d}',utc_first(-1),utc_first(0),utc_first(1),utc_first(2)

def make_router(settings:AuthSettings,calendar_enabled=False):
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

    if calendar_enabled:
        @router.get('/public/calendar')
        def public_calendar(response:Response,month:str|None=Query(default=None,max_length=7)):
            label,prev_start,start_at,end_at,next_end=_month_parts(month)
            response.headers.update(HEADERS)
            response.headers['Cache-Control']='public, max-age=0, s-maxage=60'
            try:
                data=store.public_calendar(prev_start,start_at,end_at,next_end)
            except Exception:
                logger.warning('public_calendar_store_unavailable')
                raise HTTPException(503,'calendar_unavailable',headers=HEADERS) from None
            return {'month':label,**data}

    if calendar_enabled:
        @router.get('/admin/learning/calendar')
        def admin_calendar(response:Response,admin:Annotated[Principal,Depends(require_admin)],
                           month:str|None=Query(default=None,max_length=7)):
            label,_,start_at,end_at,_=_month_parts(month)
            return {'month':label,'items':read(response,store.admin_calendar,start_at,end_at)}

    @router.get('/admin/learning/enrollments/{enrollment_id}/adjustments')
    def enrollment_adjustments(enrollment_id:UUID,response:Response,
                               admin:Annotated[Principal,Depends(require_admin)],
                               limit:int=Query(100,ge=1,le=200)):
        return read(response,store.adjustments,enrollment_id,limit)

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

    if calendar_enabled:
        @router.post('/admin/learning/calendar-events')
        def create_calendar_event(body:model.CalendarEventCreate,response:Response,
                                  admin:Annotated[Principal,Depends(permitted)]):
            return write(response,admin,'calendar_event.create',body)

        @router.post('/admin/learning/calendar-events/update')
        def update_calendar_event(body:model.CalendarEventUpdate,response:Response,
                                  admin:Annotated[Principal,Depends(permitted)]):
            return write(response,admin,'calendar_event.update',body)

    @router.post('/admin/learning/enrollments')
    def grant(body:model.EnrollmentGrant,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.grant',body)

    @router.post('/admin/learning/enrollments/cancel')
    def cancel(body:model.EnrollmentCancel,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.cancel',body)

    @router.post('/admin/learning/enrollments/restore')
    def restore(body:model.EnrollmentRestore,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.restore',body)

    @router.post('/admin/learning/enrollments/suspend')
    def suspend(body:model.EnrollmentSuspend,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.suspend',body)

    @router.post('/admin/learning/enrollments/resume')
    def resume(body:model.EnrollmentResume,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.resume',body)

    @router.post('/admin/learning/enrollments/extend')
    def extend(body:model.EnrollmentExtend,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.extend',body)

    @router.post('/admin/learning/enrollments/refund')
    def refund(body:model.EnrollmentRefund,response:Response,admin:Annotated[Principal,Depends(permitted)]):
        return write(response,admin,'enrollment.refund',body)

    return router


def install_if_enabled(app:FastAPI):
    if os.getenv('RICHON_COURSE_DOMAIN_ENABLED','false')!='true':return False
    if (os.getenv('RICHON_AUTH_ENABLED')!='true' or os.getenv('RICHON_PORTAL_ENABLED')!='true'
        or not any(getattr(r,'path',None)=='/portal/api/admin/summary' for r in app.routes)):
        raise ValueError('course_domain_requires_private_portal')
    origins=frozenset(x.strip() for x in os.getenv('RICHON_AUTH_ALLOWED_ORIGINS','').split(',') if x.strip())
    calendar_enabled=True
    app.include_router(make_router(AuthSettings(origins),calendar_enabled=calendar_enabled))

    if calendar_enabled:
        @app.get('/portal/calendar',include_in_schema=False)
        def calendar_page():return FileResponse(STATIC/'calendar.html',headers=UI_PAGE_HEADERS)

        @app.get('/portal/calendar-assets/{asset}',include_in_schema=False)
        def calendar_asset(asset:str):
            if asset not in {'calendar.css','calendar.js','calendar-logo.svg'}:raise HTTPException(404,'not_found',headers=HEADERS)
            return FileResponse(STATIC/asset,headers=HEADERS)

    @app.get('/portal/courses',include_in_schema=False)
    def page():return FileResponse(STATIC/'courses.html',headers=UI_PAGE_HEADERS)

    @app.get('/portal/course-assets/{asset}',include_in_schema=False)
    def asset(asset:str):
        if asset not in {'courses.css','courses.js'}:raise HTTPException(404,'not_found',headers=HEADERS)
        return FileResponse(STATIC/asset,headers=HEADERS)
    return True
