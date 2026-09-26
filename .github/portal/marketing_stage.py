"""Build and stage the marketing-consent code only on the protected Worker candidate.

Precondition:
- account-enabled protected candidate is current
- DB011 and exact runtime grants are owner-prepared
- marketing feature is still OFF

The operation builds the current source, creates a zero-percent revision with
RICHON_MARKETING_CONSENT_ENABLED=true, proves readiness + edge gate + immutable
configuration, then moves ONLY portal-candidate to that revision.

Default 100% Cloud Run traffic, IAM, secrets, DB, Cloudflare settings and public
homepage are not changed by this operation.
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
import account_enable_stage as a
import candidate_readback as r
import operate as op

OPERATION='stage-marketing-enabled'
READ_OPERATION='inspect-marketing-enabled'
CHECK_TAG='portal-marketing-check'
CHECK_URL='https://' + CHECK_TAG + '---' + urlsplit(c.URL).netloc


def tagged_rows(svc):
    return sorted((row.get('tag',''),row.get('revisionName'),
                   int(row.get('percent',0)),row.get('url',''))
                  for row in svc.get('status',{}).get('traffic',[]))


def worker_revision(svc):
    rows=[row for row in svc.get('status',{}).get('traffic',[]) if row.get('tag')==c.TAG]
    c.need(len(rows)==1 and int(rows[0].get('percent',0))==0
           and rows[0].get('url')==e.CANDIDATE,
           'marketing_worker_tag_required')
    name=rows[0].get('revisionName','')
    c.need(re.fullmatch(c.SERVICE+r'-[a-z0-9-]+',name),'marketing_worker_revision_invalid')
    return name


def code_revision(svc):
    return a.code_check_revision(svc)


def expected_before_rows(code_rev,worker_rev):
    return sorted([
        ('',r.SERVING,100,''),
        (c.TAG,worker_rev,0,e.CANDIDATE),
        ('portal-account-check',code_rev,0,
         'https://portal-account-check---'+urlsplit(c.URL).netloc),
    ])


def expected_staged_rows(code_rev,worker_rev,new_rev):
    return sorted(expected_before_rows(code_rev,worker_rev)+[
        (CHECK_TAG,new_rev,0,CHECK_URL),
    ])


def expected_switched_rows(code_rev,new_rev):
    return sorted([
        ('',r.SERVING,100,''),
        (c.TAG,new_rev,0,e.CANDIDATE),
        ('portal-account-check',code_rev,0,
         'https://portal-account-check---'+urlsplit(c.URL).netloc),
    ])


def intended(before,image):
    result=deepcopy(before)
    container=result['spec']['template']['spec']['containers'][0]
    env=c.environment(container)
    info=c.inspect(result,{'bindings':[{'role':'roles/run.invoker','members':['allUsers']}]},
                   require_ready=False,boundary='edge')
    # The synthetic policy above is only for config-shape validation and is not
    # compared to production IAM; the real policy is verified separately.
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is False,
           'marketing_precondition_flags_mismatch')
    env['RICHON_MARKETING_CONSENT_ENABLED']={
        'name':'RICHON_MARKETING_CONSENT_ENABLED','value':'true'}
    container['env']=list(env.values())
    container['image']=image
    return result


def intended_without_policy(before,image):
    result=deepcopy(before)
    container=result['spec']['template']['spec']['containers'][0]
    env=c.environment(container)
    c.need(env.get('RICHON_ACCOUNT_ENABLED',{}).get('value')=='true',
           'account_feature_required')
    c.need('RICHON_MARKETING_CONSENT_ENABLED' not in env,
           'marketing_feature_already_enabled')
    c.need(env.get('RICHON_TERMS_VERSION',{}).get('value')=='member-info-v1'
           and env.get('RICHON_PRIVACY_VERSION',{}).get('value')=='member-info-v1',
           'member_policy_required')
    env['RICHON_MARKETING_CONSENT_ENABLED']={
        'name':'RICHON_MARKETING_CONSENT_ENABLED','value':'true'}
    container['env']=list(env.values())
    container['image']=image
    return result


def validate_before(svc,policy):
    info=c.inspect(svc,policy,boundary='edge')
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is False,
           'marketing_precondition_flags_mismatch')
    worker=worker_revision(svc)
    code=code_revision(svc)
    c.need(tagged_rows(svc)==expected_before_rows(code,worker),
           'marketing_unexpected_existing_traffic_or_tags')
    c.need(svc['status']['latestCreatedRevisionName']==worker
           and svc['status']['latestReadyRevisionName']==worker,
           'marketing_worker_not_latest')
    a.verify_revision(worker,svc,policy)
    c.need(e.access_status()=='signin-gateway-confirmed','access_gateway_not_confirmed')
    return code,worker


def verify_revision(name,svc,policy):
    revision=c.gc('run','revisions','describe',name,'--region='+c.REGION)
    meta=revision.get('metadata',{})
    c.need(meta.get('name')==name and str(meta.get('namespace'))==c.NUMBER
           and meta.get('labels',{}).get('serving.knative.dev/service')==c.SERVICE,
           'marketing_revision_identity_mismatch')
    c.need(any(x.get('type')=='Ready' and x.get('status')=='True'
               for x in revision.get('status',{}).get('conditions',[])),
           'marketing_revision_not_ready')
    actual=deepcopy(revision.get('spec',{}))
    expected=deepcopy(svc['spec']['template']['spec'])
    c.need(len(actual.get('containers',[]))==len(expected.get('containers',[]))==1,
           'marketing_container_mismatch')
    if 'name' not in expected['containers'][0] and actual['containers'][0].get('name')=='portal-1':
        c.need(not actual['containers'][0].get('dependsOn')
               and not meta.get('annotations',{}).get('run.googleapis.com/container-dependencies'),
               'marketing_dependencies_changed')
        actual['containers'][0].pop('name')
    c.need(actual==expected,'marketing_immutable_spec_mismatch')
    view=deepcopy(svc)
    view['spec']['template']['spec']=deepcopy(revision['spec'])
    view['spec']['template']['metadata']['annotations']=deepcopy(meta.get('annotations',{}))
    view['status']['latestCreatedRevisionName']=name
    view['status']['latestReadyRevisionName']=name
    info=c.inspect(view,policy,boundary='edge')
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is True,
           'marketing_revision_flags_missing')


def verify_config(before,policy,current,current_policy,new_rev,code_rev,worker_rev,image,*,switched):
    info=c.inspect(current,current_policy,boundary='edge')
    c.need(info['revision']==new_rev and info['image']==image
           and info['account_enabled'] is True and info['marketing_enabled'] is True,
           'marketing_revision_or_flags_mismatch')
    c.need(current['status']['latestCreatedRevisionName']==new_rev
           and current['status']['latestReadyRevisionName']==new_rev,
           'marketing_candidate_not_ready')
    expected=intended_without_policy(before,image)
    c.need(c.protected(current)==c.protected(expected),
           'marketing_configuration_changed')
    c.need(c.policy_key(current_policy)==c.policy_key(policy),'marketing_iam_changed')
    c.need(c.traffic(current)==[(r.SERVING,100)],'marketing_default_traffic_changed')
    rows=(expected_switched_rows(code_rev,new_rev) if switched
          else expected_staged_rows(code_rev,worker_rev,new_rev))
    c.need(tagged_rows(current)==rows,'marketing_tags_changed')
    verify_revision(new_rev,current,current_policy)


def probe_gate(url):
    c.need(url in (CHECK_URL,e.CANDIDATE),'unsafe_marketing_probe_url')
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
                   'marketing_gate_probe_failed')
        except c.Stop:
            raise
        except Exception:
            raise c.Stop('marketing_probe_failed') from None


def inspect_current(sha):
    svc,policy=e.get_service()
    info=c.inspect(svc,policy,boundary='edge')
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is True,
           'marketing_readback_flags_missing')
    code=code_revision(svc)
    worker=worker_revision(svc)
    c.need(tagged_rows(svc)==expected_switched_rows(code,worker),
           'marketing_readback_tags_mismatch')
    c.need(c.traffic(svc)==[(r.SERVING,100)],'marketing_readback_default_traffic_changed')
    verify_revision(worker,svc,policy)
    probe_gate(e.CANDIDATE)
    c.need(e.access_status()=='signin-gateway-confirmed','access_gateway_not_confirmed')
    op.summary('MARKETING-ENABLED READBACK PASSED: '+worker)
    op.summary('SOURCE CONTROL: '+sha+' / runtime image: '+info['image'].split('@',1)[1])
    op.summary('ACCOUNT=true / MARKETING=true / policy=member-info-v1 / portal-candidate only.')
    op.summary('DEFAULT TRAFFIC UNCHANGED: '+r.SERVING+' = 100%.')
    op.summary('CLOUDFLARE ACCESS: signin gateway confirmed / READ-ONLY.')
    return 0


def run():
    sha=c.source(live=True)
    request=c.read_request()
    if request['operation']==READ_OPERATION:
        return inspect_current(sha)
    c.need(request['operation']==OPERATION,'explicit_marketing_stage_required')

    before,policy=e.get_service()
    code,old_worker=validate_before(before,policy)

    run_id=os.environ.get('GITHUB_RUN_ID','')
    attempt=os.environ.get('GITHUB_RUN_ATTEMPT','')
    c.need(re.fullmatch(r'[0-9]+',run_id) and re.fullmatch(r'[0-9]+',attempt),
           'invalid_run_identity')
    suffix='mkt-'+run_id+'-'+attempt
    revision=c.SERVICE+'-'+suffix

    tagged=c.IMAGE+':'+sha
    c.command(['gcloud','auth','configure-docker',c.REGION+'-docker.pkg.dev','--quiet'])
    c.command(['docker','push',tagged],timeout=300)
    value=c.gc('artifacts','docker','images','describe',tagged)
    digest=value.get('image_summary',{}).get('digest','')
    c.need(re.fullmatch(r'sha256:[a-f0-9]{64}',digest),'image_digest_missing')
    image=c.IMAGE+'@'+digest

    current,current_policy=e.get_service()
    c.need(current['spec']==before['spec']
           and c.policy_key(current_policy)==c.policy_key(policy)
           and tagged_rows(current)==tagged_rows(before),
           'service_changed_before_marketing_stage')
    c.source(live=True)

    c.gc('run','services','update',c.SERVICE,'--region='+c.REGION,
         '--image='+image,'--revision-suffix='+suffix,
         '--tag='+CHECK_TAG,'--no-traffic',
         '--update-env-vars=RICHON_MARKETING_CONSENT_ENABLED=true',
         timeout=600)

    current,current_policy=e.get_service()
    verify_config(before,policy,current,current_policy,revision,code,old_worker,image,switched=False)
    probe_gate(CHECK_URL)
    c.need(e.access_status()=='signin-gateway-confirmed','access_gateway_not_confirmed')

    c.gc('run','services','update-traffic',c.SERVICE,'--region='+c.REGION,
         '--update-tags='+c.TAG+'='+revision,'--remove-tags='+CHECK_TAG,timeout=180)

    current,current_policy=e.get_service()
    verify_config(before,policy,current,current_policy,revision,code,old_worker,image,switched=True)
    probe_gate(e.CANDIDATE)
    c.need(e.access_status()=='signin-gateway-confirmed','access_gateway_not_confirmed')

    op.summary('MARKETING-ENABLED WORKER CANDIDATE READY: '+revision)
    op.summary('SOURCE IMAGE: '+sha+' / '+digest)
    op.summary('RICHON_ACCOUNT_ENABLED=true / RICHON_MARKETING_CONSENT_ENABLED=true.')
    op.summary('DEFAULT TRAFFIC UNCHANGED: '+r.SERVING+' = 100%.')
    op.summary('CLOUDFLARE ACCESS: signin gateway confirmed; public homepage unchanged.')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(run())
    except (Exception,KeyboardInterrupt) as exc:
        code=str(exc) if isinstance(exc,c.Stop) else 'unexpected_marketing_stage_failure'
        print('STOP: marketing-stage / '+code+'. No raw credentials or responses printed.',
              file=sys.stderr)
        raise SystemExit(1) from None
