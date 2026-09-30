#!/usr/bin/env python3
"""Request-driven existing-service operations; never expose, migrate or read secrets."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import common as c

STAGE = 'request'


def state_path():
    root = Path(os.environ['RUNNER_TEMP']).resolve()
    c.need(not root.is_relative_to(c.ROOT.resolve()), 'unsafe_state_directory')
    return root / 'richon-portal-operation.json'


def save(value):
    path = state_path()
    c.need(not path.is_symlink(), 'unsafe_state_file')
    with open(path, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
        json.dump(value, f)
    path.chmod(0o600)


def load():
    path = state_path()
    c.need(not path.is_symlink() and path.stat().st_size < 131072, 'invalid_state_file')
    result = json.loads(path.read_text())
    c.need(result.get('sha') == os.environ.get('GITHUB_SHA') and
           result.get('run') == os.environ.get('GITHUB_RUN_ID') and
           result.get('attempt') == os.environ.get('GITHUB_RUN_ATTEMPT') and
           result.get('request') == c.read_request(), 'stale_operation_state')
    return result


def summary(text):
    # Callers supply only our fixed labels + validated revision/hash/operation fields.
    print(text, flush=True)
    target = os.environ.get('GITHUB_STEP_SUMMARY')
    if target:
        with open(target, 'a') as f:
            f.write(text + '\n\n')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(url, enabled, *, authenticated=True):
    c.need(url in (c.URL, 'https://' + c.TAG + '---' + c.URL.split('://', 1)[1]), 'unsafe_probe_url')
    headers = {}
    if authenticated:
        token = os.getenv('PORTAL_ID_TOKEN', '')
        c.need(re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token), 'id_token_missing')
        headers['Authorization'] = 'Bearer ' + token
    # Never send cookies, origin secrets, OAuth codes, or request bodies.
    request = urllib.request.Request(url + '/auth/login', headers=headers, method='GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        try:
            response = opener.open(request, timeout=40)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            body = response.read(8193)
            content_type = response.headers.get('Content-Type', '')
    except Exception:
        raise c.Stop('probe_transport_failed') from None
    if not authenticated:
        c.need(status in (401, 403), 'anonymous_invocation_not_blocked')
        return
    c.need(len(body) <= 8192 and 'application/json' in content_type, 'unexpected_probe_response')
    try:
        data = json.loads(body)
    except ValueError:
        raise c.Stop('unexpected_probe_response') from None
    c.need((status, data) == ((403, {'detail': 'edge_required'}) if enabled else
                             (503, {'detail': 'portal_not_enabled'})), 'origin_boundary_probe_failed')


def snapshot():
    global STAGE
    sha = c.source(live=True)
    request = c.read_request()
    c.need(request['operation'] != 'hold', 'no_operation_requested')
    STAGE = 'read-existing-service'
    svc, policy = c.get_service()
    details = c.inspect(svc, policy)
    c.need(len(c.traffic(svc)) == 1 and c.traffic(svc)[0][1] == 100, 'unreviewed_traffic_split')
    c.need(not any(row.get('tag') and row.get('tag') != c.TAG for row in svc['status'].get('traffic', [])), 'unexpected_traffic_tag')
    value = {'sha': sha, 'run': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
             'request': request, 'before': svc, 'policy': policy}
    save(value)
    summary('PASS: fixed richon-portal / IAM private / pinned secret references / runtime limits')
    summary('Current revision: ' + details['revision'] + ' / login configuration: ' + ('enabled' if details['enabled'] else 'disabled'))


def inspect_existing():
    global STAGE
    state = load()
    c.need(state['request']['operation'] == 'inspect', 'wrong_operation')
    STAGE = 'private-origin-probe'
    details = c.inspect(state['before'], state['policy'])
    probe(c.URL, details['enabled'], authenticated=False)
    probe(c.URL, details['enabled'])
    fresh, policy = c.get_service()
    c.need(fresh['spec'] == state['before']['spec'] and c.policy_key(policy) == c.policy_key(state['policy']), 'service_changed_during_inspection')
    summary('PORTAL INSPECT PASSED. No deployment or DB/customer writes. Real Kakao login is not tested here.')


def candidate():
    global STAGE
    state = load()
    operation = state['request']['operation']
    c.need(operation in ('deploy', 'configure-internal-login'), 'wrong_operation')
    c.source(live=True)
    before = state['before']
    current, policy = c.get_service()
    c.need(current['spec'] == before['spec'] and c.policy_key(policy) == c.policy_key(state['policy'])
           and current['status']['latestCreatedRevisionName'] == before['status']['latestCreatedRevisionName'], 'service_changed_before_update')
    sha = state['sha']
    if operation == 'deploy':
        STAGE = 'resolve-built-image'
        tagged = c.IMAGE + ':' + sha
        # Authentication exists only after the image was built and checked locally.
        c.command(['gcloud', 'auth', 'configure-docker', c.REGION + '-docker.pkg.dev', '--quiet'])
        c.command(['docker', 'push', tagged], timeout=300)
        value = c.gc('artifacts', 'docker', 'images', 'describe', tagged)
        digest = value.get('image_summary', {}).get('digest', '')
        c.need(re.fullmatch('sha256:[a-f0-9]{64}', digest), 'image_digest_missing')
        image = c.IMAGE + '@' + digest
    else:
        image = before['spec']['template']['spec']['containers'][0]['image']
    run, attempt = state['run'], state['attempt']
    c.need(re.fullmatch('[0-9]+', run) and re.fullmatch('[0-9]+', attempt), 'invalid_run_id')
    suffix = 'gh-' + run + '-' + attempt
    revision = c.SERVICE + '-' + suffix
    state.update(image=image, candidate=revision)
    save(state)  # Keep operation receipt even when candidate startup fails.
    STAGE = 'candidate-deployment'
    args = ['run', 'services', 'update', c.SERVICE, '--region=' + c.REGION,
            '--image=' + image, '--revision-suffix=' + suffix, '--tag=' + c.TAG, '--no-traffic']
    if operation == 'configure-internal-login':
        args.append('--update-env-vars=' + ','.join(k + '=' + v for k, v in c.INTERNAL.items()))
    c.gc(*args, timeout=600)
    svc, policy = c.get_service()
    verify_candidate(state, svc, policy)
    summary('CANDIDATE READY: ' + revision + '. Existing service traffic retained until checks pass.')


def verify_candidate(state, svc, policy):
    c.inspect(svc, policy)
    c.need(svc['status']['latestCreatedRevisionName'] == state['candidate'] and
           svc['status']['latestReadyRevisionName'] == state['candidate'], 'concurrent_or_unready_candidate')
    c.need(svc['spec']['template']['spec']['containers'][0]['image'] == state['image'], 'candidate_image_mismatch')
    c.need(c.protected(svc) == c.protected(c.intended(state['before'], state['request']['operation'])), 'unexpected_configuration_change')
    c.need(c.policy_key(policy) == c.policy_key(state['policy']), 'iam_policy_changed')
    c.need(c.traffic(svc) == c.traffic(state['before']), 'traffic_changed_before_verification')
    return c.candidate_url(svc, state['candidate'])


def promote():
    global STAGE
    state = load()
    c.need(state['request']['operation'] in ('deploy', 'configure-internal-login'), 'wrong_operation')
    c.source(live=True)
    svc, policy = c.get_service()
    url = verify_candidate(state, svc, policy)
    STAGE = 'candidate-private-probe'
    enabled = c.inspect(svc, policy)['enabled']
    probe(url, enabled, authenticated=False)
    probe(url, enabled)
    # Recheck after network probes to avoid overriding a concurrent owner edit.
    svc, policy = c.get_service()
    verify_candidate(state, svc, policy)
    c.source(live=True)
    STAGE = 'promote-checked-revision'
    c.gc('run', 'services', 'update-traffic', c.SERVICE, '--region=' + c.REGION,
         '--to-revisions=' + state['candidate'] + '=100', '--remove-tags=' + c.TAG, timeout=180)
    svc, policy = c.get_service()
    c.need(c.traffic(svc) == [(state['candidate'], 100)] and not any(r.get('tag') for r in svc['status'].get('traffic', [])), 'promotion_not_confirmed')
    c.need(c.policy_key(policy) == c.policy_key(state['policy']) and
           c.protected(svc) == c.protected(c.intended(state['before'], state['request']['operation'])), 'post_promotion_config_mismatch')
    c.need(svc['status']['latestCreatedRevisionName'] == state['candidate'] and
           svc['spec']['template']['spec']['containers'][0]['image'] == state['image'], 'post_promotion_revision_mismatch')
    probe(c.URL, enabled, authenticated=False)
    probe(c.URL, enabled)
    summary('PORTAL OPERATION PASSED: ' + state['request']['operation'] + ' / ' + state['candidate'])
    summary('IAM remains private. No Cloudflare/public-access or schema changes. Previous revision: ' + c.traffic(state['before'])[0][0])


def diagnose():
    # Safe metadata, not application logs or raw condition messages containing inputs.
    global STAGE
    STAGE = 'safe-diagnosis'
    try:
        svc, policy = c.get_service(require_ready=False)
        status = svc['status']
        summary('DIAGNOSTIC latest created: ' + status['latestCreatedRevisionName'])
        summary('DIAGNOSTIC latest ready: ' + status['latestReadyRevisionName'])
        ready = any(row.get('type') == 'Ready' and row.get('status') == 'True' for row in status.get('conditions', []))
        summary('DIAGNOSTIC Ready: ' + str(ready) + '. Raw application logs are not exported.')
    except c.Stop as exc:
        summary('DIAGNOSTIC: ' + str(exc))


def main():
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    actions = {'snapshot': snapshot, 'inspect': inspect_existing, 'candidate': candidate,
               'promote': promote, 'diagnose': diagnose}
    if action == 'request':
        c.source(live=True)
        print('operation=' + c.read_request()['operation'])
    else:
        c.need(action in actions, 'invalid_action')
        actions[action]()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, c.Stop) else 'unexpected_failure'
        print('STOP: ' + STAGE + ' / ' + code + '. No raw credentials or responses printed.', file=sys.stderr)
        raise SystemExit(1) from None
