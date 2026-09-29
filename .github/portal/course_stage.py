"""Enable the canonical course domain only on the protected Worker candidate.

Preconditions:
- the current portal-candidate already contains course-capable code
- migrations 015 and 016 plus reviewed runtime grants are owner-confirmed
- RICHON_COURSE_DOMAIN_ENABLED is still absent

This operation adds only the course-domain feature flag on a new zero-percent
revision, verifies the existing edge boundary and immutable configuration, then
moves only the portal-candidate tag. Default 100% Cloud Run traffic, IAM,
secrets, database contents, Cloudflare configuration and public homepage remain
unchanged.
"""
from copy import deepcopy
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import common as c
import edge_ops as e
import operate as op

OPERATION='stage-course-enabled'
READ_OPERATION='inspect-course-enabled'
CHECK_TAG='portal-course-check'
CHECK_URL='https://' + CHECK_TAG + '---' + urlsplit(c.URL).netloc


def tag_rows(svc):
    return sorted((row.get('tag',''),row.get('revisionName'),
                   int(row.get('percent',0)),row.get('url',''))
                  for row in svc.get('status',{}).get('traffic',[]))


def current_candidate(svc):
    rows=[row for row in svc.get('status',{}).get('traffic',[])
          if row.get('tag')==c.TAG]
    c.need(len(rows)==1 and int(rows[0].get('percent',0))==0
           and rows[0].get('url')==e.CANDIDATE,
           'course_candidate_tag_invalid')
    name=rows[0].get('revisionName','')
    c.need(re.fullmatch(c.SERVICE+r'-[a-z0-9-]+',name),
           'course_candidate_revision_invalid')
    return name


def serving_revision(svc):
    rows=[row for row in svc.get('status',{}).get('traffic',[])
          if not row.get('tag') and int(row.get('percent',0))==100]
    c.need(len(rows)==1,'course_default_100_required')
    name=rows[0].get('revisionName','')
    c.need(re.fullmatch(c.SERVICE+r'-[a-z0-9-]+',name),
           'course_default_revision_invalid')
    return name


def intended(before):
    result=deepcopy(before)
    container=result['spec']['template']['spec']['containers'][0]
    env=c.environment(container)
    c.need('RICHON_COURSE_DOMAIN_ENABLED' not in env,
           'course_feature_already_enabled')
    env['RICHON_COURSE_DOMAIN_ENABLED']={
        'name':'RICHON_COURSE_DOMAIN_ENABLED','value':'true'}
    container['env']=list(env.values())
    return result


def ensure_before(svc,policy):
    info=c.inspect(svc,policy,boundary='edge')
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is True,
           'course_account_marketing_precondition_failed')
    c.need(info['course_enabled'] is False,'course_feature_already_enabled')
    c.need(c.traffic(svc)==[(serving_revision(svc),100)],
           'course_default_traffic_changed')
    old=current_candidate(svc)
    c.need(not any(row.get('tag')==CHECK_TAG
                   for row in svc.get('status',{}).get('traffic',[])),
           'course_check_tag_already_exists')
    c.need(e.access_status()=='signin-gateway-confirmed',
           'course_access_gateway_not_confirmed')
    return old


def verify_revision(name,svc,policy):
    rev=c.gc('run','revisions','describe',name,'--region='+c.REGION)
    meta=rev.get('metadata',{})
    c.need(meta.get('name')==name and str(meta.get('namespace'))==c.NUMBER
           and meta.get('labels',{}).get('serving.knative.dev/service')==c.SERVICE,
           'course_revision_identity_mismatch')
    c.need(any(x.get('type')=='Ready' and x.get('status')=='True'
               for x in rev.get('status',{}).get('conditions',[])),
           'course_revision_not_ready')
    actual=deepcopy(rev.get('spec',{}))
    expected=deepcopy(svc['spec']['template']['spec'])
    c.need(len(actual.get('containers',[]))==len(expected.get('containers',[]))==1,
           'course_revision_container_mismatch')
    if 'name' not in expected['containers'][0] and actual['containers'][0].get('name')=='portal-1':
        c.need(not actual['containers'][0].get('dependsOn')
               and not meta.get('annotations',{}).get('run.googleapis.com/container-dependencies'),
               'course_revision_dependencies_changed')
        actual['containers'][0].pop('name')
    c.need(actual==expected,'course_revision_spec_mismatch')
    view=deepcopy(svc)
    view['spec']['template']['spec']=deepcopy(rev['spec'])
    view['spec']['template']['metadata']['annotations']=deepcopy(meta.get('annotations',{}))
    view['status']['latestCreatedRevisionName']=name
    view['status']['latestReadyRevisionName']=name
    info=c.inspect(view,policy,boundary='edge')
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is True
           and info['course_enabled'] is True,
           'course_revision_flags_missing')


def expected_staged(before,new_revision):
    rows=tag_rows(before)
    rows.append((CHECK_TAG,new_revision,0,CHECK_URL))
    return sorted(rows)


def expected_switched(before,new_revision):
    rows=[]
    for tag,revision,percent,url in tag_rows(before):
        if tag==c.TAG:
            rows.append((tag,new_revision,0,e.CANDIDATE))
        else:
            rows.append((tag,revision,percent,url))
    return sorted(rows)


def verify_config(before,before_policy,current,current_policy,new_revision,*,switched):
    info=c.inspect(current,current_policy,boundary='edge')
    c.need(info['course_enabled'] is True and info['account_enabled'] is True
           and info['marketing_enabled'] is True,
           'course_runtime_flags_mismatch')
    c.need(current['status']['latestCreatedRevisionName']==new_revision
           and current['status']['latestReadyRevisionName']==new_revision,
           'course_latest_revision_mismatch')
    expected=intended(before)
    c.need(c.protected(current)==c.protected(expected),
           'course_protected_configuration_changed')
    c.need(c.policy_key(current_policy)==c.policy_key(before_policy),
           'course_iam_changed')
    c.need(c.traffic(current)==c.traffic(before),
           'course_default_traffic_changed')
    rows=expected_switched(before,new_revision) if switched else expected_staged(before,new_revision)
    c.need(tag_rows(current)==rows,'course_tags_changed')
    verify_revision(new_revision,current,current_policy)


def probe_gate(url):
    c.need(url in (CHECK_URL,e.CANDIDATE),'unsafe_course_probe_url')
    for wrong in (False,True):
        headers={'Accept':'text/html','User-Agent':e.PROBE_USER_AGENT}
        if wrong:
            headers['X-Richon-Edge-Key']='deliberately-invalid-test-key'
        request=urllib.request.Request(url+'/auth/login',headers=headers,method='GET')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),op.NoRedirect())
        try:
            try:
                response=opener.open(request,timeout=25)
            except urllib.error.HTTPError as exc:
                response=exc
            with response:
                status=response.code
                content_type=response.headers.get('Content-Type','').split(';')[0]
                body=response.read(8193)
            c.need(status==403 and content_type=='application/json' and len(body)<=8192
                   and json.loads(body)=={'detail':'edge_required'},
                   'course_edge_gate_failed')
        except c.Stop:
            raise
        except Exception:
            raise c.Stop('course_edge_gate_probe_failed') from None


def stage():
    c.source(live=True)
    req=c.read_request()
    c.need(req['operation']==OPERATION,'explicit_course_stage_required')
    before,before_policy=e.get_service()
    old=current_candidate(before)
    ensure_before(before,before_policy)

    run_id,attempt=os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT']
    c.need(re.fullmatch('[0-9]+',run_id) and re.fullmatch('[0-9]+',attempt),
           'invalid_course_run_identity')
    suffix='course-'+run_id+'-'+attempt
    new_revision=c.SERVICE+'-'+suffix

    c.gc('run','services','update',c.SERVICE,'--region='+c.REGION,
         '--revision-suffix='+suffix,'--tag='+CHECK_TAG,'--no-traffic',
         '--update-env-vars=RICHON_COURSE_DOMAIN_ENABLED=true',timeout=600)
    staged,staged_policy=e.get_service()
    verify_config(before,before_policy,staged,staged_policy,new_revision,switched=False)
    probe_gate(CHECK_URL)
    c.need(e.access_status()=='signin-gateway-confirmed',
           'course_access_gateway_changed')

    c.gc('run','services','update-traffic',c.SERVICE,'--region='+c.REGION,
         '--update-tags='+c.TAG+'='+new_revision,'--remove-tags='+CHECK_TAG,timeout=180)
    current,current_policy=e.get_service()
    verify_config(before,before_policy,current,current_policy,new_revision,switched=True)
    probe_gate(e.CANDIDATE)
    c.need(e.access_status()=='signin-gateway-confirmed',
           'course_access_gateway_changed_after_switch')
    op.summary('COURSE DOMAIN ENABLED ON PROTECTED CANDIDATE: '+new_revision)
    op.summary('Default 100% revision unchanged: '+serving_revision(current))
    op.summary('Previous protected candidate: '+old)
    op.summary('DB migrations are not executed by this operation.')


def inspect():
    c.source(live=True)
    req=c.read_request()
    c.need(req['operation']==READ_OPERATION,'explicit_course_inspect_required')
    svc,policy=e.get_service()
    info=c.inspect(svc,policy,boundary='edge')
    c.need(info['course_enabled'] is True and info['account_enabled'] is True
           and info['marketing_enabled'] is True,
           'course_runtime_not_enabled')
    c.need(c.traffic(svc)==[(serving_revision(svc),100)],
           'course_default_traffic_changed')
    current_candidate(svc)
    c.need(not any(row.get('tag')==CHECK_TAG
                   for row in svc.get('status',{}).get('traffic',[])),
           'course_check_tag_not_removed')
    probe_gate(e.CANDIDATE)
    c.need(e.access_status()=='signin-gateway-confirmed',
           'course_access_gateway_not_confirmed')
    op.summary('COURSE DOMAIN INSPECT PASSED. No DB/IAM/secret/customer writes.')


if __name__=='__main__':
    try:
        operation=c.read_request()['operation']
        if operation==OPERATION:
            stage()
        elif operation==READ_OPERATION:
            inspect()
        else:
            raise c.Stop('course_stage_wrong_operation')
    except (Exception,KeyboardInterrupt) as exc:
        code=str(exc) if isinstance(exc,c.Stop) else 'unexpected_course_stage_failure'
        print('STOP: course stage / '+code+'. No raw credentials printed.',file=sys.stderr)
        raise SystemExit(1) from None
