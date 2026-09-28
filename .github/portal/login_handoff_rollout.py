"""Safely roll the current login-handoff code to the protected portal candidate.

Preconditions:
- the current portal-candidate is edge-gated, account-enabled and marketing-enabled
- default Cloud Run traffic remains 100% on the existing serving revision
- current IAM, env, secrets, runtime settings and every unrelated traffic tag are preserved

This operation builds/pushes the current branch image, creates a separate 0% check
revision, validates the edge gate and immutable configuration, then moves ONLY the
portal-candidate tag to the new revision. It never promotes default traffic.
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

OPERATION='rollout-login-handoff'
CHECK_TAG='portal-handoff-check'
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
           'handoff_candidate_tag_invalid')
    name=rows[0].get('revisionName','')
    c.need(re.fullmatch(c.SERVICE+r'-[a-z0-9-]+',name),
           'handoff_candidate_revision_invalid')
    return name


def serving_revision(svc):
    rows=[row for row in svc.get('status',{}).get('traffic',[])
          if not row.get('tag') and int(row.get('percent',0))==100]
    c.need(len(rows)==1,'handoff_default_100_required')
    name=rows[0].get('revisionName','')
    c.need(re.fullmatch(c.SERVICE+r'-[a-z0-9-]+',name),
           'handoff_default_revision_invalid')
    return name


def ensure_before(svc,policy):
    info=c.inspect(svc,policy,boundary='edge')
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is True,
           'handoff_features_must_remain_enabled')
    c.need(c.traffic(svc)==[(serving_revision(svc),100)],
           'handoff_default_traffic_changed')
    old=current_candidate(svc)
    c.need(not any(row.get('tag')==CHECK_TAG for row in svc.get('status',{}).get('traffic',[])),
           'handoff_check_tag_already_exists')
    c.need(e.access_status()=='signin-gateway-confirmed',
           'handoff_access_gateway_not_confirmed')
    return old,info


def without_image(svc):
    result=deepcopy(svc)
    result['spec']['template']['spec']['containers'][0].pop('image',None)
    return result


def verify_revision(name,svc,policy):
    rev=c.gc('run','revisions','describe',name,'--region='+c.REGION)
    meta=rev.get('metadata',{})
    c.need(meta.get('name')==name and str(meta.get('namespace'))==c.NUMBER
           and meta.get('labels',{}).get('serving.knative.dev/service')==c.SERVICE,
           'handoff_revision_identity_mismatch')
    c.need(any(x.get('type')=='Ready' and x.get('status')=='True'
               for x in rev.get('status',{}).get('conditions',[])),
           'handoff_revision_not_ready')
    actual=deepcopy(rev.get('spec',{}))
    expected=deepcopy(svc['spec']['template']['spec'])
    c.need(len(actual.get('containers',[]))==len(expected.get('containers',[]))==1,
           'handoff_revision_container_mismatch')
    if 'name' not in expected['containers'][0] and actual['containers'][0].get('name')=='portal-1':
        c.need(not actual['containers'][0].get('dependsOn')
               and not meta.get('annotations',{}).get('run.googleapis.com/container-dependencies'),
               'handoff_revision_dependencies_changed')
        actual['containers'][0].pop('name')
    c.need(actual==expected,'handoff_revision_spec_mismatch')
    view=deepcopy(svc)
    view['spec']['template']['spec']=deepcopy(rev['spec'])
    view['spec']['template']['metadata']['annotations']=deepcopy(meta.get('annotations',{}))
    view['status']['latestCreatedRevisionName']=name
    view['status']['latestReadyRevisionName']=name
    info=c.inspect(view,policy,boundary='edge')
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is True,
           'handoff_revision_features_changed')


def expected_staged(before,new_revision):
    rows=tag_rows(before)
    rows.append((CHECK_TAG,new_revision,0,CHECK_URL))
    return sorted(rows)


def expected_switched(before,new_revision):
    result=[]
    for tag,revision,percent,url in tag_rows(before):
        if tag==c.TAG:
            result.append((tag,new_revision,0,e.CANDIDATE))
        else:
            result.append((tag,revision,percent,url))
    return sorted(result)


def verify_config(before,before_policy,current,current_policy,new_revision,image,*,switched):
    info=c.inspect(current,current_policy,boundary='edge')
    c.need(info['revision']==new_revision and info['image']==image
           and info['account_enabled'] is True and info['marketing_enabled'] is True,
           'handoff_revision_or_features_mismatch')
    c.need(current['status']['latestCreatedRevisionName']==new_revision
           and current['status']['latestReadyRevisionName']==new_revision,
           'handoff_latest_revision_mismatch')
    c.need(c.protected(current)==c.protected(before),
           'handoff_protected_configuration_changed')
    c.need(c.policy_key(current_policy)==c.policy_key(before_policy),
           'handoff_iam_changed')
    c.need(c.traffic(current)==c.traffic(before),
           'handoff_default_traffic_changed')
    rows=expected_switched(before,new_revision) if switched else expected_staged(before,new_revision)
    c.need(tag_rows(current)==rows,'handoff_tags_changed')
    verify_revision(new_revision,current,current_policy)


def probe_gate(url):
    c.need(url in (CHECK_URL,e.CANDIDATE),'unsafe_handoff_probe_url')
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
                   'handoff_edge_gate_probe_failed')
        except c.Stop:
            raise
        except Exception:
            raise c.Stop('handoff_edge_gate_probe_failed') from None


def run():
    sha=c.source(live=True)
    request=c.read_request()
    c.need(request['operation']==OPERATION,'explicit_handoff_rollout_required')

    before,policy=e.get_service()
    old_candidate,info=ensure_before(before,policy)

    run_id=os.environ.get('GITHUB_RUN_ID','')
    attempt=os.environ.get('GITHUB_RUN_ATTEMPT','')
    c.need(re.fullmatch(r'[0-9]+',run_id) and re.fullmatch(r'[0-9]+',attempt),
           'invalid_handoff_run_identity')
    suffix='handoff-'+run_id+'-'+attempt
    revision=c.SERVICE+'-'+suffix

    tagged=c.IMAGE+':'+sha
    c.command(['gcloud','auth','configure-docker',c.REGION+'-docker.pkg.dev','--quiet'])
    c.command(['docker','push',tagged],timeout=300)
    value=c.gc('artifacts','docker','images','describe',tagged)
    digest=value.get('image_summary',{}).get('digest','')
    c.need(re.fullmatch(r'sha256:[a-f0-9]{64}',digest),'handoff_image_digest_missing')
    image=c.IMAGE+'@'+digest

    current,current_policy=e.get_service()
    c.need(current['spec']==before['spec']
           and c.policy_key(current_policy)==c.policy_key(policy)
           and tag_rows(current)==tag_rows(before),
           'handoff_service_changed_before_stage')
    c.source(live=True)

    c.gc('run','services','update',c.SERVICE,'--region='+c.REGION,
         '--image='+image,'--revision-suffix='+suffix,
         '--tag='+CHECK_TAG,'--no-traffic',timeout=600)

    staged,staged_policy=e.get_service()
    verify_config(before,policy,staged,staged_policy,revision,image,switched=False)
    probe_gate(CHECK_URL)

    fresh,fresh_policy=e.get_service()
    c.need(fresh['spec']==staged['spec']
           and c.policy_key(fresh_policy)==c.policy_key(staged_policy)
           and tag_rows(fresh)==tag_rows(staged),
           'handoff_service_changed_during_probe')
    verify_config(before,policy,fresh,fresh_policy,revision,image,switched=False)
    c.source(live=True)

    c.gc('run','services','update-traffic',c.SERVICE,'--region='+c.REGION,
         '--update-tags='+c.TAG+'='+revision,'--remove-tags='+CHECK_TAG,timeout=180)

    final,final_policy=e.get_service()
    verify_config(before,policy,final,final_policy,revision,image,switched=True)
    probe_gate(e.CANDIDATE)
    c.need(e.access_status()=='signin-gateway-confirmed',
           'handoff_access_gateway_changed')

    stable,stable_policy=e.get_service()
    c.need(stable['spec']==final['spec']
           and c.policy_key(stable_policy)==c.policy_key(final_policy)
           and tag_rows(stable)==tag_rows(final),
           'handoff_service_changed_after_switch')
    verify_config(before,policy,stable,stable_policy,revision,image,switched=True)

    op.summary('LOGIN HANDOFF CANDIDATE ROLLOUT=PASS')
    op.summary('SOURCE='+sha+' / IMAGE_DIGEST='+digest)
    op.summary('OLD_CANDIDATE='+old_candidate+' / NEW_CANDIDATE='+revision)
    op.summary('ACCOUNT=true / MARKETING=true / policy=member-info-v1')
    op.summary('DEFAULT_100_PERCENT_UNCHANGED='+serving_revision(before))
    op.summary('IAM_UNCHANGED=PASS / EDGE_GATE=PASS / ACCESS_GATE=PASS')
    op.summary('PUBLIC HOMEPAGE LOGIN ENTRY UNCHANGED.')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(run())
    except (Exception,KeyboardInterrupt) as exc:
        code=str(exc) if isinstance(exc,c.Stop) else 'unexpected_handoff_rollout_failure'
        print('STOP: login-handoff-rollout / '+code+'. No raw credentials or responses printed.',
              file=sys.stderr)
        raise SystemExit(1) from None
