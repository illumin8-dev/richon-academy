"""Stage latest account-capable code as a separate zero-traffic check revision.

This is a recovery-safe bridge after owner-run DB010 grants: old revisions may
fail their historical exact-grant startup check, while the new code must prove
it can start with account routes still OFF. This operation never moves the
existing Worker tag, default traffic, IAM, secrets, policy versions, or DB.
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
import candidate_readback as r
import operate as op

OPERATION = 'stage-account-code'
CHECK_TAG = 'portal-account-check'
CHECK_URL = 'https://' + CHECK_TAG + '---' + urlsplit(c.URL).netloc
ALLOWED_EXISTING_ORIGIN_STATES = frozenset({
    'missing-key:403:edge_required,wrong-key:403:edge_required',
    'missing-key:500:non_json,wrong-key:500:non_json',
    'missing-key:500:non_json,wrong-key:503:non_json',
    'missing-key:503:non_json,wrong-key:500:non_json',
    'missing-key:503:non_json,wrong-key:503:non_json',
})


def tagged_rows(svc):
    return sorted((row.get('tag',''), row.get('revisionName'),
                   int(row.get('percent',0)), row.get('url',''))
                  for row in svc.get('status',{}).get('traffic',[]))


def expected_rows(new_revision=None):
    rows = [
        ('', r.SERVING, 100, ''),
        (c.TAG, r.CANDIDATE, 0, e.CANDIDATE),
    ]
    if new_revision:
        rows.append((CHECK_TAG, new_revision, 0, CHECK_URL))
    return sorted(rows)


def account_feature_off(svc):
    env = c.environment(svc['spec']['template']['spec']['containers'][0])
    c.need('RICHON_ACCOUNT_ENABLED' not in env, 'account_feature_must_remain_off')
    return True


def validate_before(svc, policy):
    r.validate_service(svc, policy)
    c.need(tagged_rows(svc) == expected_rows(), 'unexpected_existing_traffic_or_tags')
    account_feature_off(svc)
    revisions = {name:c.gc('run','revisions','describe',name,'--region='+c.REGION)
                 for name in (r.CANDIDATE,r.SERVING)}
    for name, revision in revisions.items():
        r.validate_revision(revision,name,svc,policy)
    c.need(e.access_status() == 'signin-gateway-confirmed', 'access_gateway_not_confirmed')
    serving = r.safe_origin_observation(c.URL)
    candidate = r.safe_origin_observation(e.CANDIDATE)
    op.summary('EXISTING SERVING ORIGIN: ' + serving)
    op.summary('EXISTING WORKER CANDIDATE ORIGIN: ' + candidate)
    c.need(serving in ALLOWED_EXISTING_ORIGIN_STATES, 'unexpected_serving_origin_state')
    c.need(candidate in ALLOWED_EXISTING_ORIGIN_STATES, 'unexpected_candidate_origin_state')
    return revisions


def verify_revision(revision_name, svc, policy):
    revision = c.gc('run','revisions','describe',revision_name,'--region='+c.REGION)
    meta = revision.get('metadata',{})
    c.need(meta.get('name') == revision_name and str(meta.get('namespace')) == c.NUMBER
           and meta.get('labels',{}).get('serving.knative.dev/service') == c.SERVICE,
           'account_stage_revision_identity_mismatch')
    c.need(any(x.get('type')=='Ready' and x.get('status')=='True'
               for x in revision.get('status',{}).get('conditions',[])),
           'account_stage_revision_not_ready')
    actual = deepcopy(revision.get('spec',{}))
    expected = deepcopy(svc['spec']['template']['spec'])
    c.need(len(actual.get('containers',[])) == len(expected.get('containers',[])) == 1,
           'account_stage_container_mismatch')
    if 'name' not in expected['containers'][0] and actual['containers'][0].get('name') == 'portal-1':
        c.need(not actual['containers'][0].get('dependsOn')
               and not meta.get('annotations',{}).get('run.googleapis.com/container-dependencies'),
               'account_stage_dependencies_changed')
        actual['containers'][0].pop('name')
    c.need(actual == expected, 'account_stage_immutable_spec_mismatch')
    view = deepcopy(svc)
    view['spec']['template']['spec'] = deepcopy(revision['spec'])
    view['spec']['template']['metadata']['annotations'] = deepcopy(meta.get('annotations',{}))
    view['status']['latestCreatedRevisionName'] = revision_name
    view['status']['latestReadyRevisionName'] = revision_name
    c.inspect(view,policy,boundary='edge')


def verify_staged(before, before_policy, current, current_policy, revision, image):
    info = c.inspect(current,current_policy,boundary='edge')
    c.need(info['revision'] == revision and info['image'] == image,
           'account_stage_revision_or_image_mismatch')
    c.need(current['status']['latestCreatedRevisionName'] == revision
           and current['status']['latestReadyRevisionName'] == revision,
           'account_stage_candidate_not_ready')
    c.need(c.protected(current) == c.protected(before), 'account_stage_configuration_changed')
    c.need(c.policy_key(current_policy) == c.policy_key(before_policy), 'account_stage_iam_changed')
    c.need(c.traffic(current) == [(r.SERVING,100)], 'account_stage_default_traffic_changed')
    c.need(tagged_rows(current) == expected_rows(revision), 'account_stage_tags_changed')
    account_feature_off(current)
    verify_revision(revision,current,current_policy)


def probe_check_tag():
    for wrong in (False,True):
        headers = {'Accept':'text/html','User-Agent':e.PROBE_USER_AGENT}
        if wrong:
            headers['X-Richon-Edge-Key'] = 'deliberately-invalid-test-key'
        request = urllib.request.Request(CHECK_URL + '/auth/login',headers=headers,method='GET')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),op.NoRedirect())
        try:
            try:
                response = opener.open(request,timeout=25)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                status=response.code
                content_type=response.headers.get('Content-Type','').split(';')[0]
                body=response.read(8193)
            c.need(status == 403 and content_type == 'application/json' and len(body) <= 8192
                   and json.loads(body) == {'detail':'edge_required'},
                   'account_stage_gate_probe_failed')
        except c.Stop:
            raise
        except Exception:
            raise c.Stop('account_stage_probe_failed') from None


def run():
    sha = c.source(live=True)
    request = c.read_request()
    c.need(request['operation'] == OPERATION, 'explicit_account_stage_required')

    before, policy = e.get_service()
    validate_before(before,policy)

    run_id=os.environ.get('GITHUB_RUN_ID','')
    attempt=os.environ.get('GITHUB_RUN_ATTEMPT','')
    c.need(re.fullmatch(r'[0-9]+',run_id) and re.fullmatch(r'[0-9]+',attempt),
           'invalid_run_identity')
    suffix='acct-' + run_id + '-' + attempt
    revision=c.SERVICE + '-' + suffix

    tagged=c.IMAGE + ':' + sha
    c.command(['gcloud','auth','configure-docker',c.REGION+'-docker.pkg.dev','--quiet'])
    c.command(['docker','push',tagged],timeout=300)
    value=c.gc('artifacts','docker','images','describe',tagged)
    digest=value.get('image_summary',{}).get('digest','')
    c.need(re.fullmatch(r'sha256:[a-f0-9]{64}',digest),'image_digest_missing')
    image=c.IMAGE + '@' + digest

    current,current_policy=e.get_service()
    e.unchanged(before,policy,current,current_policy)
    account_feature_off(current)
    c.source(live=True)

    c.gc('run','services','update',c.SERVICE,'--region='+c.REGION,
         '--image='+image,'--revision-suffix='+suffix,
         '--tag='+CHECK_TAG,'--no-traffic',timeout=600)

    current,current_policy=e.get_service()
    verify_staged(before,policy,current,current_policy,revision,image)
    probe_check_tag()

    fresh,fresh_policy=e.get_service()
    c.need(fresh['spec'] == current['spec']
           and c.policy_key(fresh_policy) == c.policy_key(current_policy)
           and tagged_rows(fresh) == tagged_rows(current),
           'account_stage_changed_during_probe')
    verify_staged(before,policy,fresh,fresh_policy,revision,image)

    op.summary('ACCOUNT CODE CHECK REVISION READY: ' + revision)
    op.summary('SOURCE IMAGE: ' + sha + ' / ' + digest)
    op.summary('ACCOUNT_FEATURE=OFF / portal-account-check traffic=0%.')
    op.summary('EXISTING WORKER TAG UNCHANGED: ' + r.CANDIDATE)
    op.summary('DEFAULT TRAFFIC UNCHANGED: ' + r.SERVING + ' = 100%.')
    op.summary('NOT PROMOTED. No IAM, secret, DB, Cloudflare or provider changes.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(run())
    except (Exception,KeyboardInterrupt) as exc:
        code=str(exc) if isinstance(exc,c.Stop) else 'unexpected_account_stage_failure'
        print('STOP: account-code-stage / '+code+'. No raw credentials or responses printed.',
              file=sys.stderr)
        raise SystemExit(1) from None
