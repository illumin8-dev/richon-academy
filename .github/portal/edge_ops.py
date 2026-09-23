#!/usr/bin/env python3
"""Explicit edge-gated inspection or zero-traffic staging, never auto-promotion.

No IAM/secret/schema changes. No provider or customer calls. Existing private
operations remain private. Staging cannot be substituted for a migration check.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import common as c
import operate as op

ORIGIN = 'https://richonacademy.com'
ACCESS_HOST = 'raspy-bush-b23c.cloudflareaccess.com'
CANDIDATE = 'https://' + c.TAG + '---' + urlsplit(c.URL).netloc
PATHS = ('/auth/login', '/auth/kakao/callback', '/portal/mypage')
PUBLIC = ('/', '/apply.html')
URLS = {c.URL + '/auth/login', CANDIDATE + '/auth/login'} | {ORIGIN + p for p in PATHS + PUBLIC}


def get_service():
    svc = c.gc('run', 'services', 'describe', c.SERVICE, '--region=' + c.REGION)
    policy = c.gc('run', 'services', 'get-iam-policy', c.SERVICE, '--region=' + c.REGION)
    c.inspect(svc, policy, boundary='edge')
    return svc, policy


def request(url, *, wrong_key=False):
    c.need(url in URLS, 'unsafe_probe_url')
    c.need(not wrong_key or url in {c.URL + '/auth/login', CANDIDATE + '/auth/login'},
           'unsafe_probe_header')
    headers = {'X-Richon-Edge-Key': 'deliberately-invalid-test-key'} if wrong_key else {}
    req = urllib.request.Request(url, headers=headers, method='GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), op.NoRedirect())
    try:
        try:
            response = opener.open(req, timeout=25)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.code, response.headers, response.read(8193)
    except Exception:
        raise c.Stop('edge_probe_transport_failed') from None


def probe_origin(url):
    c.need(url in (c.URL, CANDIDATE), 'unsafe_probe_url')
    for wrong in (False, True):
        status, headers, body = request(url + '/auth/login', wrong_key=wrong)
        c.need(status == 403 and headers.get('Content-Type', '').split(';')[0] == 'application/json'
               and len(body) <= 8192, 'origin_app_gate_not_confirmed')
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            raise c.Stop('origin_app_gate_not_confirmed') from None
        c.need(data == {'detail': 'edge_required'}, 'origin_app_gate_not_confirmed')


def access_status():
    """Evidence of an Access sign-in gateway, NOT proof of its email allow rule.

    403 alone is inconclusive (runner/WAF/network may block it), never a PASS.
    No raw redirects, query strings, cookies, or page bodies are logged.
    """
    try:
        for path in PATHS:
            status, headers, _ = request(ORIGIN + path)
            target = urlsplit(headers.get('Location', ''))
            if not (status in (302, 303) and target.scheme == 'https'
                    and target.netloc == ACCESS_HOST and not target.username
                    and target.path == '/cdn-cgi/access/login/richonacademy.com'):
                return 'inconclusive'
        for path in PUBLIC:
            status, headers, _ = request(ORIGIN + path)
            if status != 200 or 'text/html' not in headers.get('Content-Type', ''):
                return 'inconclusive'
    except (c.Stop, ValueError):
        return 'inconclusive'
    return 'signin-gateway-confirmed'


def unchanged(before, policy, current, current_policy):
    c.need(current['spec'] == before['spec'] and c.protected(current) == c.protected(before)
           and c.traffic(current) == c.traffic(before)
           and c.policy_key(current_policy) == c.policy_key(policy)
           and current['status']['latestCreatedRevisionName'] == before['status']['latestCreatedRevisionName'],
           'service_changed_during_edge_operation')


def verify_candidate(state, svc, policy):
    c.inspect(svc, policy, boundary='edge')
    c.need(svc['status']['latestCreatedRevisionName'] == state['candidate']
           and svc['status']['latestReadyRevisionName'] == state['candidate'], 'candidate_not_ready')
    c.need(svc['spec']['template']['spec']['containers'][0]['image'] == state['image'], 'candidate_image_mismatch')
    c.need(c.protected(svc) == c.protected(state['before']), 'unexpected_configuration_change')
    c.need(c.policy_key(policy) == c.policy_key(state['policy']), 'iam_policy_changed')
    c.need(c.traffic(svc) == c.traffic(state['before']), 'traffic_changed_during_staging')
    c.need(all(not row.get('tag') or row.get('tag') == c.TAG for row in svc['status'].get('traffic', [])),
           'unexpected_traffic_tag')
    return c.candidate_url(svc, state['candidate'])


def stage(state):
    """Only a candidate image is changed. No code path promotes it to customers."""
    c.need(state['request']['operation'] == 'stage-edge', 'wrong_operation')
    c.need(state['access'] == 'signin-gateway-confirmed', 'access_gateway_not_confirmed')
    c.source(live=True)
    current, policy = get_service()
    unchanged(state['before'], state['policy'], current, policy)
    c.need(access_status() == 'signin-gateway-confirmed', 'access_gateway_not_confirmed')
    probe_origin(c.URL)
    tagged = c.IMAGE + ':' + state['sha']
    c.command(['gcloud', 'auth', 'configure-docker', c.REGION + '-docker.pkg.dev', '--quiet'])
    c.command(['docker', 'push', tagged], timeout=300)
    value = c.gc('artifacts', 'docker', 'images', 'describe', tagged)
    digest = value.get('image_summary', {}).get('digest', '')
    c.need(re.fullmatch(r'sha256:[a-f0-9]{64}', digest), 'image_digest_missing')
    run, attempt = state['run'], state['attempt']
    c.need(re.fullmatch('[0-9]+', run) and re.fullmatch('[0-9]+', attempt), 'invalid_run_id')
    suffix = 'gh-' + run + '-' + attempt
    state.update(image=c.IMAGE + '@' + digest, candidate=c.SERVICE + '-' + suffix)
    op.save(state)
    # Check again after image upload, before the one service configuration write.
    current, policy = get_service()
    unchanged(state['before'], state['policy'], current, policy)
    c.source(live=True)
    c.gc('run', 'services', 'update', c.SERVICE, '--region=' + c.REGION,
         '--image=' + state['image'], '--revision-suffix=' + suffix,
         '--tag=' + c.TAG, '--no-traffic', timeout=600)
    current, policy = get_service()
    url = verify_candidate(state, current, policy)
    probe_origin(url)
    probe_origin(c.URL)
    current, policy = get_service()
    verify_candidate(state, current, policy)
    op.summary('EDGE CANDIDATE STAGED: ' + state['candidate'] + ' / existing 100% traffic unchanged.')
    op.summary('NOT PROMOTED. Verify database migration, real cookies and login before a separate promotion approval.')


def main():
    sha = c.source(live=True)
    req = c.read_request()
    c.need(req['operation'] in ('inspect-edge', 'stage-edge'), 'wrong_operation')
    svc, policy = get_service()
    info = c.inspect(svc, policy, boundary='edge')
    c.need(c.traffic(svc) == [(info['revision'], 100)]
           and not any(row.get('tag') for row in svc['status'].get('traffic', [])),
           'existing_candidate_or_traffic_split_requires_review')
    op.summary('PASS: fixed richon-portal / existing public invoker / enabled app gate / pinned secret references / runtime limits')
    op.summary('Current revision: ' + info['revision'])
    op.summary('Naver runtime binding: absent. No Naver enablement or secret payload access in this operation.')
    probe_origin(c.URL)
    op.summary('PASS: missing and wrong origin keys both denied by application (403 edge_required).')
    access = access_status()
    op.summary('Access gateway check: ' + access + '. Owner email policy contents are not inspected here.')
    current, fresh_policy = get_service()
    unchanged(svc, policy, current, fresh_policy)
    state = {'sha': sha, 'run': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
             'request': req, 'before': svc, 'policy': policy, 'access': access}
    op.save(state)
    if req['operation'] == 'stage-edge':
        stage(state)
    else:
        op.summary('EDGE INSPECT FINISHED: no deployment / IAM / schema / customer writes.')
        op.summary('Database migration 008: NOT CHECKED. Real Kakao authentication: NOT CHECKED. This is not launch readiness.')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, c.Stop) else 'unexpected_failure'
        print('STOP: edge-operation / ' + code + '. No raw credentials or responses printed.', file=sys.stderr)
        raise SystemExit(1) from None
