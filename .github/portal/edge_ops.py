#!/usr/bin/env python3
"""Explicit edge-gated inspection or zero-traffic staging, never auto-promotion.

No IAM/secret/schema changes. No provider or customer calls. Existing private
operations remain private. Staging cannot be substituted for a migration check.
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
import operate as op

ORIGIN = 'https://richonacademy.com'
ACCESS_HOST = 'raspy-bush-b23c.cloudflareaccess.com'
CANDIDATE = 'https://' + c.TAG + '---' + urlsplit(c.URL).netloc
CALLBACKS = ('/auth/kakao/callback', '/auth/naver/callback')
PATHS = ('/auth/login', *CALLBACKS, '/portal/mypage')
CUSTOMER_ROUTES = 'customer-routes-confirmed'
STAGE_OPERATIONS = ('stage-edge', 'stage-edge-naver')
# A public diagnostic label, NOT a credential or an authenticated identity.
# Allows the owner to scope a BIC-only exception without browser impersonation.
PROBE_USER_AGENT = 'RichonPortalDeployCheck/1.0'
# Exact versions confirmed by owner helper 0e1190bd in CHECKPOINT-019.
NAVER_VERSIONS = {'NAVER_CLIENT_ID': ('richon-naver-client-id', '1'),
                  'NAVER_CLIENT_SECRET': ('richon-naver-client-secret', '1')}
PUBLIC = ('/', '/apply.html')
PUBLIC_CALENDAR_URL = ORIGIN + '/portal/api/public/calendar'
LOGIN_MODAL = ORIGIN + '/auth/login?view=modal&return_to=%2Fportal%2Fmypage'
URLS = ({c.URL + '/auth/login', CANDIDATE + '/auth/login', LOGIN_MODAL, PUBLIC_CALENDAR_URL}
        | {ORIGIN + p for p in PATHS + PUBLIC})


def get_service():
    svc = c.gc('run', 'services', 'describe', c.SERVICE, '--region=' + c.REGION)
    policy = c.gc('run', 'services', 'get-iam-policy', c.SERVICE, '--region=' + c.REGION)
    c.inspect(svc, policy, boundary='edge')
    return svc, policy


def request(url, *, wrong_key=False, accept='text/html'):
    c.need(url in URLS, 'unsafe_probe_url')
    c.need(accept in ('text/html', 'application/json'), 'unsafe_probe_accept')
    c.need(not wrong_key or url in {c.URL + '/auth/login', CANDIDATE + '/auth/login'},
           'unsafe_probe_header')
    headers = {'Accept': accept, 'User-Agent': PROBE_USER_AGENT}
    if wrong_key:
        headers['X-Richon-Edge-Key'] = 'deliberately-invalid-test-key'
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
    """Verify the released customer auth/portal boundary without credentials.

    The historical function name is retained for call-site compatibility, but
    Cloudflare Access redirects are now a failure: customer /auth and /portal
    routes must reach the Worker/app. Cloud Run origin protection is checked
    separately by probe_origin().
    """
    confirmed = True
    for path in PATHS + PUBLIC:
        try:
            status, headers, _ = request(ORIGIN + path)
            target = urlsplit(headers.get('Location', ''))
            access_redirect = (status in (302, 303) and target.scheme == 'https'
                               and target.netloc == ACCESS_HOST and not target.username
                               and target.path == '/cdn-cgi/access/login/richonacademy.com')
            html_page = status == 200 and 'text/html' in headers.get('Content-Type', '')
            callback_fallback = (
                path in CALLBACKS and status == 303
                and target.scheme == 'https' and target.netloc == urlsplit(ORIGIN).netloc
                and not target.username and target.path == '/auth/login'
                and target.query == 'error=login_failed'
            )
            # Cloudflare Pages canonicalizes top-level HTML files to extensionless
            # URLs. Accept only the exact observed/supported /apply.html -> /apply
            # permanent redirect; no other public redirect is treated as healthy.
            pages_canonical_redirect = (
                path == '/apply.html' and status == 308
                and headers.get('Location') in ('/apply', ORIGIN + '/apply')
            )
            if path in CALLBACKS:
                passed = callback_fallback
            else:
                passed = html_page or pages_canonical_redirect
            op.summary('CUSTOMER ROUTE PROBE ' + path + ': ' + json.dumps({
                'status': status, 'expected_response': passed,
                'access_redirect': access_redirect,
                'cloudflare_marker': bool(headers.get('CF-Ray')),
                'challenge': headers.get('CF-Mitigated') == 'challenge',
            }, sort_keys=True))
            confirmed = confirmed and passed and not access_redirect
        except (c.Stop, ValueError):
            confirmed = False
            op.summary('CUSTOMER ROUTE PROBE ' + path + ': transport_or_redirect_unconfirmed')

    try:
        status, headers, body = request(LOGIN_MODAL, accept='application/json')
        valid = status == 200 and headers.get('Content-Type', '').split(';')[0] == 'application/json' and len(body) <= 8192
        if valid:
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError):
                valid = False
            else:
                valid = (
                    isinstance(data, dict)
                    and bool(re.fullmatch(r'[a-f0-9]{64}', data.get('csrf', '')))
                    and data.get('return_to') == '/portal/mypage'
                    and isinstance(data.get('providers'), list)
                    and 1 <= len(data['providers']) <= 2
                    and len(set(data['providers'])) == len(data['providers'])
                    and set(data['providers']) <= {'kakao', 'naver'}
                )
        op.summary('CUSTOMER ROUTE PROBE login-modal: ' + json.dumps({
            'status': status, 'expected_response': valid,
            'cloudflare_marker': bool(headers.get('CF-Ray')),
            'challenge': headers.get('CF-Mitigated') == 'challenge',
        }, sort_keys=True))
        confirmed = confirmed and valid
    except (c.Stop, ValueError):
        confirmed = False
        op.summary('CUSTOMER ROUTE PROBE login-modal: transport_or_response_unconfirmed')

    try:
        status, headers, body = request(PUBLIC_CALENDAR_URL, accept='application/json')
        valid = (
            status == 200
            and headers.get('Content-Type', '').split(';')[0] == 'application/json'
            and headers.get('Cache-Control', '') == 'public, max-age=0, s-maxage=60'
            and not headers.get('Set-Cookie')
            and len(body) <= 8192
        )
        if valid:
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError):
                valid = False
            else:
                valid = (
                    isinstance(data, dict)
                    and bool(re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', data.get('month', '')))
                    and isinstance(data.get('items'), list)
                    and isinstance(data.get('has_prev'), bool)
                    and isinstance(data.get('has_next'), bool)
                )
        op.summary('CUSTOMER ROUTE PROBE public-calendar: ' + json.dumps({
            'status': status, 'expected_response': valid,
            'cache_control': headers.get('Cache-Control', ''),
            'cloudflare_marker': bool(headers.get('CF-Ray')),
            'challenge': headers.get('CF-Mitigated') == 'challenge',
        }, sort_keys=True))
        confirmed = confirmed and valid
    except (c.Stop, ValueError):
        confirmed = False
        op.summary('CUSTOMER ROUTE PROBE public-calendar: transport_or_response_unconfirmed')
    return CUSTOMER_ROUTES if confirmed else 'inconclusive'


def candidate_configuration(before, operation):
    """Only this explicitly requested mode may add the two approved refs."""
    c.need(operation in STAGE_OPERATIONS, 'wrong_stage_operation')
    result = deepcopy(before)
    if operation == 'stage-edge-naver':
        container = result['spec']['template']['spec']['containers'][0]
        env = c.environment(container)
        refs = c.naver_references(env, boundary='edge')
        approved = {name: {'name': name, 'valueFrom': {
            'secretKeyRef': {'name': secret, 'key': version}}}
            for name, (secret, version) in NAVER_VERSIONS.items()}
        c.need(not refs or refs == approved, 'naver_version_changed_requires_review')
        env.update(approved)
        container['env'] = list(env.values())
    return result


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
    c.need(c.protected(svc) == c.protected(candidate_configuration(state['before'], state['request']['operation'])), 'unexpected_configuration_change')
    c.need(c.policy_key(policy) == c.policy_key(state['policy']), 'iam_policy_changed')
    c.need(c.traffic(svc) == c.traffic(state['before']), 'traffic_changed_during_staging')
    c.need(all(not row.get('tag') or row.get('tag') == c.TAG for row in svc['status'].get('traffic', [])),
           'unexpected_traffic_tag')
    return c.candidate_url(svc, state['candidate'])


def stage(state):
    """Only a candidate image is changed. No code path promotes it to customers."""
    c.need(state['request']['operation'] in STAGE_OPERATIONS, 'wrong_operation')
    intended = candidate_configuration(state['before'], state['request']['operation'])
    c.inspect(intended, state['policy'], boundary='edge')
    c.need(state['access'] == CUSTOMER_ROUTES, 'customer_routes_not_confirmed')
    c.source(live=True)
    current, policy = get_service()
    unchanged(state['before'], state['policy'], current, policy)
    c.need(access_status() == CUSTOMER_ROUTES, 'customer_routes_not_confirmed')
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
    args = ['run', 'services', 'update', c.SERVICE, '--region=' + c.REGION,
            '--image=' + state['image'], '--revision-suffix=' + suffix,
            '--tag=' + c.TAG, '--no-traffic']
    if state['request']['operation'] == 'stage-edge-naver':
        args.append('--update-secrets=' + ','.join(
            name + '=' + secret + ':' + version
            for name, (secret, version) in NAVER_VERSIONS.items()))
    c.gc(*args, timeout=600)
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
    c.need(req['operation'] in ('inspect-edge',) + STAGE_OPERATIONS, 'wrong_operation')
    svc, policy = get_service()
    info = c.inspect(svc, policy, boundary='edge')
    c.need(c.traffic(svc) == [(info['revision'], 100)]
           and not any(row.get('tag') for row in svc['status'].get('traffic', [])),
           'existing_candidate_or_traffic_split_requires_review')
    op.summary('PASS: fixed richon-portal / existing public invoker / enabled app gate / pinned secret references / runtime limits')
    op.summary('Current revision: ' + info['revision'])
    env = c.environment(svc['spec']['template']['spec']['containers'][0])
    naver = c.naver_references(env, boundary='edge')
    op.summary('Naver runtime binding: ' + ('paired pinned references present' if naver else 'absent') +
               '. No provider-key payloads were inspected.')
    probe_origin(c.URL)
    op.summary('PASS: missing and wrong origin keys both denied by application (403 edge_required).')
    access = access_status()
    op.summary('Customer route check: ' + access + '. Cloudflare Access redirects are not accepted on customer auth/portal routes.')
    current, fresh_policy = get_service()
    unchanged(svc, policy, current, fresh_policy)
    state = {'sha': sha, 'run': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
             'request': req, 'before': svc, 'policy': policy, 'access': access}
    op.save(state)
    if req['operation'] in STAGE_OPERATIONS:
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
