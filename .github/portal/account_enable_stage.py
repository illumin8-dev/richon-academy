"""Enable account actions only on the protected Worker candidate.

Precondition: DB010/grants are owner-prepared and the latest account-capable image
has already been staged under portal-account-check with account actions OFF.

This operation creates one zero-percent account-enabled revision, proves its edge
gate and immutable configuration, then moves ONLY the existing portal-candidate
tag to it. The default 100% Cloud Run revision, IAM, secrets, DB, Cloudflare
configuration and public homepage are not changed. Real provider login remains a
separate owner browser action behind Cloudflare Access.
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
import account_stage as code_stage
import candidate_readback as r
import operate as op

OPERATION='stage-account-enabled'
CHECK_TAG='portal-account-livecheck'
CHECK_URL='https://' + CHECK_TAG + '---' + urlsplit(c.URL).netloc


def tagged_rows(svc):
    return sorted((row.get('tag',''),row.get('revisionName'),
                   int(row.get('percent',0)),row.get('url',''))
                  for row in svc.get('status',{}).get('traffic',[]))


def code_check_revision(svc):
    rows=[row for row in svc.get('status',{}).get('traffic',[])
          if row.get('tag')==code_stage.CHECK_TAG]
    c.need(len(rows)==1 and int(rows[0].get('percent',0))==0
           and rows[0].get('url')==code_stage.CHECK_URL
           and re.fullmatch(c.SERVICE+r'-acct-[0-9]+-[0-9]+',rows[0].get('revisionName','')),
           'account_code_check_tag_required')
    return rows[0]['revisionName']


def expected_before_rows(code_revision):
    return sorted([
        ('',r.SERVING,100,''),
        (c.TAG,r.CANDIDATE,0,e.CANDIDATE),
        (code_stage.CHECK_TAG,code_revision,0,code_stage.CHECK_URL),
    ])


def expected_staged_rows(code_revision,new_revision):
    return sorted(expected_before_rows(code_revision)+[
        (CHECK_TAG,new_revision,0,CHECK_URL),
    ])


def expected_switched_rows(code_revision,new_revision):
    return sorted([
        ('',r.SERVING,100,''),
        (c.TAG,new_revision,0,e.CANDIDATE),
        (code_stage.CHECK_TAG,code_revision,0,code_stage.CHECK_URL),
    ])


def intended(before):
    result=deepcopy(before)
    container=result['spec']['template']['spec']['containers'][0]
    env=c.environment(container)
    c.need('RICHON_ACCOUNT_ENABLED' not in env,'account_feature_already_enabled')
    c.need(env.get('RICHON_TERMS_VERSION',{}).get('value')==c.INTERNAL['RICHON_TERMS_VERSION']
           and env.get('RICHON_PRIVACY_VERSION',{}).get('value')==c.INTERNAL['RICHON_PRIVACY_VERSION'],
           'unexpected_pre_account_policy')
    env.update({
        'RICHON_ACCOUNT_ENABLED':{'name':'RICHON_ACCOUNT_ENABLED','value':'true'},
        'RICHON_TERMS_VERSION':{'name':'RICHON_TERMS_VERSION','value':c.ACCOUNT['RICHON_TERMS_VERSION']},
        'RICHON_PRIVACY_VERSION':{'name':'RICHON_PRIVACY_VERSION','value':c.ACCOUNT['RICHON_PRIVACY_VERSION']},
    })
    container['env']=list(env.values())
    return result


def validate_before(svc,policy):
    info=c.inspect(svc,policy,boundary='edge')
    c.need(info['account_enabled'] is False,'account_feature_already_enabled')
    code_revision=code_check_revision(svc)
    c.need(tagged_rows(svc)==expected_before_rows(code_revision),
           'unexpected_existing_traffic_or_tags')
    c.need(svc['status']['latestCreatedRevisionName']==code_revision
           and svc['status']['latestReadyRevisionName']==code_revision,
           'account_code_check_not_latest')
    code_stage.verify_revision(code_revision,svc,policy)
    c.need(e.access_status()=='signin-gateway-confirmed','access_gateway_not_confirmed')
    candidate=intended(svc)
    account=c.inspect(candidate,policy,boundary='edge')
    c.need(account['account_enabled'] is True,'account_candidate_not_enabled')
    return code_revision,candidate


def verify_revision(revision_name,svc,policy):
    revision=c.gc('run','revisions','describe',revision_name,'--region='+c.REGION)
    meta=revision.get('metadata',{})
    c.need(meta.get('name')==revision_name and str(meta.get('namespace'))==c.NUMBER
           and meta.get('labels',{}).get('serving.knative.dev/service')==c.SERVICE,
           'account_enabled_revision_identity_mismatch')
    c.need(any(x.get('type')=='Ready' and x.get('status')=='True'
               for x in revision.get('status',{}).get('conditions',[])),
           'account_enabled_revision_not_ready')
    actual=deepcopy(revision.get('spec',{}))
    expected=deepcopy(svc['spec']['template']['spec'])
    c.need(len(actual.get('containers',[]))==len(expected.get('containers',[]))==1,
           'account_enabled_container_mismatch')
    if 'name' not in expected['containers'][0] and actual['containers'][0].get('name')=='portal-1':
        c.need(not actual['containers'][0].get('dependsOn')
               and not meta.get('annotations',{}).get('run.googleapis.com/container-dependencies'),
               'account_enabled_dependencies_changed')
        actual['containers'][0].pop('name')
    c.need(actual==expected,'account_enabled_immutable_spec_mismatch')
    view=deepcopy(svc)
    view['spec']['template']['spec']=deepcopy(revision['spec'])
    view['spec']['template']['metadata']['annotations']=deepcopy(meta.get('annotations',{}))
    view['status']['latestCreatedRevisionName']=revision_name
    view['status']['latestReadyRevisionName']=revision_name
    info=c.inspect(view,policy,boundary='edge')
    c.need(info['account_enabled'] is True,'account_enabled_revision_flag_missing')


def verify_config(before,policy,current,current_policy,new_revision,code_revision,*,switched):
    info=c.inspect(current,current_policy,boundary='edge')
    c.need(info['account_enabled'] is True and info['revision']==new_revision,
           'account_enabled_revision_or_flag_mismatch')
    c.need(current['status']['latestCreatedRevisionName']==new_revision
           and current['status']['latestReadyRevisionName']==new_revision,
           'account_enabled_candidate_not_ready')
    c.need(c.protected(current)==c.protected(intended(before)),
           'account_enabled_configuration_changed')
    c.need(c.policy_key(current_policy)==c.policy_key(policy),'account_enabled_iam_changed')
    c.need(c.traffic(current)==[(r.SERVING,100)],'account_enabled_default_traffic_changed')
    expected=(expected_switched_rows(code_revision,new_revision) if switched
              else expected_staged_rows(code_revision,new_revision))
    c.need(tagged_rows(current)==expected,'account_enabled_tags_changed')
    verify_revision(new_revision,current,current_policy)


def probe_gate(url):
    c.need(url in (CHECK_URL,e.CANDIDATE),'unsafe_account_probe_url')
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
                   'account_enabled_gate_probe_failed')
        except c.Stop:
            raise
        except Exception:
            raise c.Stop('account_enabled_probe_failed') from None


def rollback_worker_tag(old_revision):
    try:
        c.gc('run','services','update-traffic',c.SERVICE,'--region='+c.REGION,
             '--update-tags='+c.TAG+'='+old_revision,'--remove-tags='+CHECK_TAG,timeout=180)
    except Exception:
        raise c.Stop('account_enabled_rollback_failed') from None


def run():
    sha=c.source(live=True)
    request=c.read_request()
    c.need(request['operation']==OPERATION,'explicit_account_enable_stage_required')

    before,policy=e.get_service()
    code_revision,_=validate_before(before,policy)
    old_worker=r.CANDIDATE
    image=before['spec']['template']['spec']['containers'][0]['image']
    c.need(re.fullmatch(re.escape(c.IMAGE)+r'@sha256:[a-f0-9]{64}',image),
           'account_enabled_image_not_pinned')

    run_id=os.environ.get('GITHUB_RUN_ID','')
    attempt=os.environ.get('GITHUB_RUN_ATTEMPT','')
    c.need(re.fullmatch(r'[0-9]+',run_id) and re.fullmatch(r'[0-9]+',attempt),
           'invalid_run_identity')
    suffix='accton-'+run_id+'-'+attempt
    revision=c.SERVICE+'-'+suffix

    current,current_policy=e.get_service()
    c.need(current['spec']==before['spec']
           and c.policy_key(current_policy)==c.policy_key(policy)
           and tagged_rows(current)==tagged_rows(before),
           'service_changed_before_account_enable')
    c.source(live=True)

    c.gc('run','services','update',c.SERVICE,'--region='+c.REGION,
         '--image='+image,'--revision-suffix='+suffix,
         '--tag='+CHECK_TAG,'--no-traffic',
         '--update-env-vars=RICHON_ACCOUNT_ENABLED=true,RICHON_TERMS_VERSION=member-info-v1,RICHON_PRIVACY_VERSION=member-info-v1',
         timeout=600)

    current,current_policy=e.get_service()
    verify_config(before,policy,current,current_policy,revision,code_revision,switched=False)
    probe_gate(CHECK_URL)
    c.need(e.access_status()=='signin-gateway-confirmed','access_gateway_not_confirmed')

    # The Worker upstream is the fixed portal-candidate tag. Move only that tag.
    c.gc('run','services','update-traffic',c.SERVICE,'--region='+c.REGION,
         '--update-tags='+c.TAG+'='+revision,'--remove-tags='+CHECK_TAG,timeout=180)
    try:
        current,current_policy=e.get_service()
        verify_config(before,policy,current,current_policy,revision,code_revision,switched=True)
        probe_gate(e.CANDIDATE)
        c.need(e.access_status()=='signin-gateway-confirmed','access_gateway_not_confirmed')
        fresh,fresh_policy=e.get_service()
        c.need(fresh['spec']==current['spec']
               and c.policy_key(fresh_policy)==c.policy_key(current_policy)
               and tagged_rows(fresh)==tagged_rows(current),
               'account_enabled_changed_during_probe')
        verify_config(before,policy,fresh,fresh_policy,revision,code_revision,switched=True)
    except Exception:
        rollback_worker_tag(old_worker)
        raise

    op.summary('ACCOUNT-ENABLED WORKER CANDIDATE READY: '+revision)
    op.summary('SOURCE CONTROL: '+sha+' / runtime image unchanged: '+image.split('@',1)[1])
    op.summary('RICHON_ACCOUNT_ENABLED=true / policy=member-info-v1 / candidate tag only.')
    op.summary('DEFAULT TRAFFIC UNCHANGED: '+r.SERVING+' = 100%.')
    op.summary('CLOUDFLARE ACCESS: signin gateway confirmed; public homepage checks unchanged.')
    op.summary('REAL PROVIDER CALLS NOT AUTOMATED. Owner browser verification is now ready.')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(run())
    except (Exception,KeyboardInterrupt) as exc:
        code=str(exc) if isinstance(exc,c.Stop) else 'unexpected_account_enable_stage_failure'
        print('STOP: account-enable-stage / '+code+'. No raw credentials or responses printed.',
              file=sys.stderr)
        raise SystemExit(1) from None
