"""Explicit code-only rollout for PR24; keep collection disabled and Access intact.

The existing Worker tag is live traffic even at 0%. Create a separate protected
check tag, verify readiness and missing/wrong-key denial, then move the live tag.
No DB/secret/IAM/policy-version writes. This is NOT member-info-v1 activation.
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
import candidate_readback as r
import edge_ops as e
import operate as op

CODE = '9ae550a9bc53fed5e0e785f3a9fb21b274730cc5'
CHECK_TAG = 'portal-code-check'
CHECK_URL = 'https://' + CHECK_TAG + '---' + urlsplit(c.URL).netloc
REPORT = {'code_deployed': False, 'collection_activated': False, 'database_009': 'not_checked'}


def tagged_rows(svc):
    return sorted((x.get('tag', ''), x.get('revisionName'), int(x.get('percent', 0)), x.get('url', ''))
                  for x in svc['status'].get('traffic', []))


def tags(svc, live_revision, check_revision=None):
    expected = [(c.TAG, live_revision, 0, e.CANDIDATE), ('', r.SERVING, 100, '')]
    if check_revision is not None:
        expected.append((CHECK_TAG, check_revision, 0, CHECK_URL))
    c.need(tagged_rows(svc) == sorted(expected), 'unexpected_rollout_traffic_or_tags')
    # Reject mutable LATEST percentages and unexpected desired tag routes too.
    desired = svc['spec'].get('traffic', [])
    if desired:
        c.need(all(not row.get('latestRevision', False) and row.get('revisionName')
                   for row in desired), 'mutable_traffic_target')
        observed = sorted((t, n, p) for t, n, p, _ in tagged_rows(svc))
        wanted = sorted((x.get('tag', ''), x.get('revisionName'), int(x.get('percent', 0))) for x in desired)
        c.need(wanted == observed, 'desired_traffic_not_converged')


def verify_new(state, svc, policy, *, switched=False):
    info = c.inspect(svc, policy, boundary='edge')
    c.need(info['revision'] == state['candidate'] and info['image'] == state['image'],
           'rollout_revision_or_image_mismatch')
    c.need(c.protected(svc) == c.protected(state['before']), 'rollout_configuration_changed')
    c.need(c.policy_key(policy) == c.policy_key(state['policy']), 'rollout_iam_changed')
    tags(svc, state['candidate'] if switched else r.CANDIDATE,
         None if switched else state['candidate'])


def verify_new_revision(state, svc, policy):
    name = state['candidate']
    rev = c.gc('run', 'revisions', 'describe', name, '--region=' + c.REGION)
    meta = rev.get('metadata', {})
    c.need(meta.get('name') == name and str(meta.get('namespace')) == c.NUMBER
           and meta.get('labels', {}).get('serving.knative.dev/service') == c.SERVICE,
           'rollout_revision_identity_mismatch')
    c.need(any(x.get('type') == 'Ready' and x.get('status') == 'True'
               for x in rev.get('status', {}).get('conditions', [])), 'rollout_revision_not_ready')
    actual = deepcopy(rev.get('spec', {}))
    expected = svc['spec']['template']['spec']
    c.need(len(actual.get('containers', [])) == len(expected['containers']) == 1,
           'rollout_container_mismatch')
    if 'name' not in expected['containers'][0] and actual['containers'][0].get('name') == 'portal-1':
        c.need(not actual['containers'][0].get('dependsOn')
               and not meta.get('annotations', {}).get('run.googleapis.com/container-dependencies'),
               'rollout_dependencies_changed')
        actual['containers'][0].pop('name')
    c.need(actual == expected, 'rollout_immutable_spec_mismatch')
    view = deepcopy(svc)
    view['spec']['template']['spec'] = deepcopy(rev['spec'])
    view['spec']['template']['metadata']['annotations'] = deepcopy(meta.get('annotations', {}))
    c.inspect(view, policy, boundary='edge')


def probe_check_tag():
    # The URL is a fixed Cloud Run tag. Never accept caller-supplied hosts/paths.
    for wrong in (False, True):
        headers = {'Accept': 'text/html', 'User-Agent': e.PROBE_USER_AGENT}
        if wrong:
            headers['X-Richon-Edge-Key'] = 'deliberately-invalid-test-key'
        req = urllib.request.Request(CHECK_URL + '/auth/login', headers=headers, method='GET')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), op.NoRedirect())
        try:
            try:
                response = opener.open(req, timeout=25)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                status = response.code
                content_type = response.headers.get('Content-Type', '').split(';')[0]
                body = response.read(8193)
            c.need(status == 403 and content_type == 'application/json' and len(body) <= 8192
                   and json.loads(body) == {'detail': 'edge_required'}, 'check_tag_gate_failed')
        except c.Stop:
            raise
        except Exception:
            raise c.Stop('check_tag_probe_failed') from None


def before_checks(svc, policy):
    info = r.validate_service(svc, policy)
    tags(svc, r.CANDIDATE)
    for name in (r.CANDIDATE, r.SERVING):
        revision = c.gc('run', 'revisions', 'describe', name, '--region=' + c.REGION)
        r.validate_revision(revision, name, svc, policy)
    image = c.gc('artifacts', 'docker', 'images', 'describe', c.IMAGE + ':' + r.SOURCE)
    digest = image.get('image_summary', {}).get('digest', '')
    c.need(re.fullmatch(r'sha256:[a-f0-9]{64}', digest)
           and info['image'] == c.IMAGE + '@' + digest, 'previous_candidate_digest_changed')
    c.need(e.access_status() == 'signin-gateway-confirmed', 'access_gateway_not_confirmed')
    e.probe_origin(c.URL)
    e.probe_origin(e.CANDIDATE)


def run():
    sha = c.source(live=True)
    req = c.read_request()
    c.need(req['operation'] == 'rollout-edge-code', 'explicit_code_rollout_required')
    c.command(['git', 'merge-base', '--is-ancestor', CODE, 'HEAD'])
    svc, policy = e.get_service()
    before_checks(svc, policy)
    current, current_policy = e.get_service()
    e.unchanged(svc, policy, current, current_policy)
    run_id, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    c.need(re.fullmatch('[0-9]+', run_id) and re.fullmatch('[0-9]+', attempt), 'invalid_run_identity')
    suffix = 'gh-' + run_id + '-' + attempt
    state = {'sha': sha, 'run': run_id, 'attempt': attempt, 'request': req,
             'before': svc, 'policy': policy, 'candidate': c.SERVICE + '-' + suffix}
    c.command(['gcloud', 'auth', 'configure-docker', c.REGION + '-docker.pkg.dev', '--quiet'])
    c.command(['docker', 'push', c.IMAGE + ':' + sha], timeout=300)
    image = c.gc('artifacts', 'docker', 'images', 'describe', c.IMAGE + ':' + sha)
    digest = image.get('image_summary', {}).get('digest', '')
    c.need(re.fullmatch(r'sha256:[a-f0-9]{64}', digest), 'image_digest_missing')
    state['image'] = c.IMAGE + '@' + digest
    op.save(state)
    REPORT.update(source_sha=sha, new_revision=state['candidate'], image_digest=digest,
                  previous_live_revision=r.CANDIDATE, default_revision=r.SERVING)
    current, current_policy = e.get_service()
    e.unchanged(svc, policy, current, current_policy)
    c.source(live=True)
    c.need(e.access_status() == 'signin-gateway-confirmed', 'access_gateway_not_confirmed')
    REPORT['stage'] = 'create_separate_check_candidate'
    c.gc('run', 'services', 'update', c.SERVICE, '--region=' + c.REGION,
         '--image=' + state['image'], '--revision-suffix=' + suffix,
         '--tag=' + CHECK_TAG, '--no-traffic', timeout=600)
    current, current_policy = e.get_service()
    verify_new(state, current, current_policy)
    verify_new_revision(state, current, current_policy)
    probe_check_tag()
    c.need(e.access_status() == 'signin-gateway-confirmed', 'access_gateway_not_confirmed')
    fresh, fresh_policy = e.get_service()
    e.unchanged(current, current_policy, fresh, fresh_policy)
    verify_new(state, fresh, fresh_policy)
    c.source(live=True)
    REPORT['stage'] = 'switch_existing_worker_tag'
    # Only tag routing changes: the default service percentage stays untouched.
    c.gc('run', 'services', 'update-traffic', c.SERVICE, '--region=' + c.REGION,
         '--update-tags=' + c.TAG + '=' + state['candidate'], '--remove-tags=' + CHECK_TAG, timeout=180)
    current, current_policy = e.get_service()
    verify_new(state, current, current_policy, switched=True)
    verify_new_revision(state, current, current_policy)
    e.probe_origin(c.URL)
    e.probe_origin(e.CANDIDATE)
    c.need(e.access_status() == 'signin-gateway-confirmed', 'access_gateway_not_confirmed')
    fresh, fresh_policy = e.get_service()
    e.unchanged(current, current_policy, fresh, fresh_policy)
    verify_new(state, fresh, fresh_policy, switched=True)
    REPORT.update(stage='verified', code_deployed=True,
                  policy_version='internal-test-v1', worker_url_unchanged=True)
    op.summary('PR24 CODE ROLLOUT VERIFIED. The live Worker tag now points to the new revision.')
    op.summary('COLLECTION REMAINS DISABLED: member-info-v1 not enabled; no DB009, policy, IAM or secret changes.')
    op.summary(json.dumps(REPORT, sort_keys=True))


if __name__ == '__main__':
    try:
        run()
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, c.Stop) else 'unexpected_rollout_failure'
        print('STOP: code-only rollout / ' + code + '. No raw credentials printed.', file=sys.stderr)
        print(json.dumps(REPORT, sort_keys=True))
        raise SystemExit(1) from None
