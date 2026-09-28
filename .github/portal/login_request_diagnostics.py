"""Read-only login request diagnosis for the protected portal candidate.

Prints only fixed route categories, status codes, counts and timestamps.
Never prints request bodies, query strings, cookies, CSRF, OAuth code/state,
provider tokens, customer data, secrets or application exception payloads.
"""
from collections import Counter
import json
import re
from urllib.parse import urlsplit

import common as c
import edge_ops as e

OPERATION='inspect-login-requests'
ALLOWED_PATHS={'/auth/login','/auth/start','/auth/assets/handoff.js','/auth/kakao/callback','/auth/naver/callback'}


def candidate_revision(svc):
    rows=[row for row in svc.get('status',{}).get('traffic',[])
          if row.get('tag')==c.TAG]
    c.need(len(rows)==1 and int(rows[0].get('percent',0))==0,
           'candidate_tag_missing')
    name=rows[0].get('revisionName','')
    c.need(re.fullmatch(c.SERVICE+r'-[a-z0-9-]+',name),
           'candidate_revision_invalid')
    return name


def read_logs(revision):
    result=[]
    for wanted in sorted(ALLOWED_PATHS):
        filt=(
            'resource.type="cloud_run_revision" AND '
            f'resource.labels.service_name="{c.SERVICE}" AND '
            f'httpRequest.requestUrl:"{wanted}"'
        )
        raw=c.command(['gcloud','logging','read',filt,'--project='+c.PROJECT,
                       '--freshness=15m','--limit=40','--order=asc','--format=json'],
                      timeout=90)
        try:
            rows=json.loads(raw) if raw.strip() else []
        except (ValueError,UnicodeError):
            raise c.Stop('invalid_log_response') from None
        c.need(isinstance(rows,list),'invalid_log_response')
        for row in rows:
            req=row.get('httpRequest') or {}
            method=req.get('requestMethod')
            status=req.get('status')
            url=req.get('requestUrl','')
            try:
                path=urlsplit(url).path
            except ValueError:
                continue
            if path != wanted or method not in {'GET','POST'} or not isinstance(status,int):
                continue
            stamp=row.get('timestamp','')
            if not isinstance(stamp,str) or len(stamp)>40:
                stamp=''
            rev=(row.get('resource') or {}).get('labels',{}).get('revision_name','')
            if not isinstance(rev,str) or not re.fullmatch(c.SERVICE+r'-[a-z0-9-]+',rev):
                rev='unknown'
            result.append((stamp,path,method,status,rev))
    return sorted(result)


def warning_count(revision):
    filt=(
        'resource.type="cloud_run_revision" AND '
        f'resource.labels.service_name="{c.SERVICE}" AND '
        f'resource.labels.revision_name="{revision}" AND '
        'textPayload="oauth_flow_not_completed"'
    )
    raw=c.command(['gcloud','logging','read',filt,'--project='+c.PROJECT,
                   '--freshness=15m','--limit=50','--format=json'],timeout=120)
    try:
        rows=json.loads(raw) if raw.strip() else []
    except (ValueError,UnicodeError):
        raise c.Stop('invalid_warning_log_response') from None
    c.need(isinstance(rows,list),'invalid_warning_log_response')
    return len(rows)


def classify_handoff_errors(revision):
    filt=(
        'resource.type="cloud_run_revision" AND '
        f'resource.labels.service_name="{c.SERVICE}" AND '
        f'resource.labels.revision_name="{revision}" AND '
        'logName:"run.googleapis.com%2Fstderr"'
    )
    raw=c.command(['gcloud','logging','read',filt,'--project='+c.PROJECT,
                   '--freshness=45m','--limit=200','--order=desc','--format=json'],
                  timeout=120)
    try:
        rows=json.loads(raw) if raw.strip() else []
    except (ValueError,UnicodeError):
        raise c.Stop('invalid_error_log_response') from None
    c.need(isinstance(rows,list),'invalid_error_log_response')
    joined='\n'.join(row.get('textPayload','') for row in rows
                     if isinstance(row.get('textPayload'),str)).lower()
    categories={
        'file_not_found': ('no such file or directory','filenotfounderror','does not exist'),
        'file_response': ('fileresponse','file at path'),
        'permission': ('permissionerror','permission denied'),
        'traceback': ('traceback (most recent call last)',),
        'handoff_path': ('handoff.js',),
    }
    result={}
    for key,markers in categories.items():
        count=sum(joined.count(marker) for marker in markers)
        if count:
            result[key]=count
    return result



def route_error_summary(revision):
    filt=(
        'resource.type="cloud_run_revision" AND '
        f'resource.labels.service_name="{c.SERVICE}" AND '
        f'resource.labels.revision_name="{revision}" AND '
        'severity>=ERROR'
    )
    raw=c.command(['gcloud','logging','read',filt,'--project='+c.PROJECT,
                   '--freshness=30m','--limit=100','--order=asc','--format=json'],
                  timeout=90)
    try:
        rows=json.loads(raw) if raw.strip() else []
    except (ValueError,UnicodeError):
        raise c.Stop('invalid_error_log_response') from None
    c.need(isinstance(rows,list),'invalid_error_log_response')
    counts=Counter()
    for row in rows:
        text=row.get('textPayload')
        if not isinstance(text,str):
            continue
        # Fixed safe categories only. Never print arbitrary traceback lines or payloads.
        category='other_error'
        if 'File at path' in text and 'does not exist' in text:
            category='missing_static_file'
        elif 'RuntimeError' in text and 'FileResponse' in text:
            category='file_response_runtime_error'
        elif 'Traceback' in text:
            category='python_traceback'
        counts[category]+=1
    for category,count in sorted(counts.items()):
        print(f'ERROR_CATEGORY {category} count={count}')

def run():
    c.source(live=True)
    req=c.read_request()
    c.need(req['operation']==OPERATION,'explicit_login_diagnostics_required')
    svc,policy=e.get_service()
    revision=candidate_revision(svc)
    c.inspect(svc,policy,boundary='edge')
    rows=read_logs(revision)
    counts=Counter((path,method,status,rev) for _,path,method,status,rev in rows)

    print('LOGIN_REQUEST_DIAGNOSTICS=READ_ONLY')
    print('CANDIDATE_REVISION='+revision)
    print('WINDOW=15m')
    print('REQUEST_COUNT='+str(len(rows)))
    for (path,method,status,rev),count in sorted(counts.items()):
        labels={
            '/auth/login':'LOGIN_PAGE','/auth/start':'AUTH_START',
            '/auth/assets/handoff.js':'HANDOFF_ASSET',
            '/auth/kakao/callback':'KAKAO_CALLBACK',
            '/auth/naver/callback':'NAVER_CALLBACK',
        }
        print(f'{labels[path]} {method} status={status} revision={rev} count={count}')
    starts=[row for row in rows if row[1]=='/auth/start']
    print('AUTH_START_TOTAL='+str(len(starts)))
    for index,(stamp,_,method,status,rev) in enumerate(starts[-20:],1):
        print(f'AUTH_START_EVENT_{index} timestamp={stamp} method={method} status={status} revision={rev}')
    print('OAUTH_FLOW_NOT_COMPLETED_WARNINGS='+str(warning_count(revision)))
    route_error_summary(revision)
    errors=classify_handoff_errors(revision)
    for key,count in sorted(errors.items()):
        print('HANDOFF_ERROR_CLASS='+key+' count='+str(count))
    print('NO_BODIES_OR_QUERY_STRINGS_PRINTED=YES')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(run())
    except (Exception,KeyboardInterrupt) as exc:
        code=str(exc) if isinstance(exc,c.Stop) else 'unexpected_login_diagnostics_failure'
        print('STOP: login-request-diagnostics / '+code+'. No raw logs or credentials printed.')
        raise SystemExit(1) from None
