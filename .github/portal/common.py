"""Fixed-target private portal automation. No DB/provider calls or secret reads."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
PROJECT = 'richon-academy'
NUMBER = '756298505437'
REGION = 'asia-southeast1'
SERVICE = 'richon-portal'
URL = 'https://richon-portal-amjmgyepbq-as.a.run.app'
RUNTIME = f'richon-portal@{PROJECT}.iam.gserviceaccount.com'
DEPLOYER = f'richon-portal-deploy@{PROJECT}.iam.gserviceaccount.com'
REGISTRY = 'richon-portal-ci'
IMAGE = f'{REGION}-docker.pkg.dev/{PROJECT}/{REGISTRY}/portal'
REPO = 'illumin8-dev/richon-academy'
REPO_ID = '1380040761'
OWNER_ID = '251193658'
BRANCH = 'feat/backend-portal-deploy'
REF = 'refs/heads/' + BRANCH
BASE = '565b02fa590fa8c7ba8e2e540fb3edd83445e887'
WORKFLOW = f'{REPO}/.github/workflows/portal-deploy.yml@{REF}'
POOL = 'richon-github-portal'
PROVIDER = 'github-portal'
POOL_PATH = f'projects/{NUMBER}/locations/global/workloadIdentityPools/{POOL}'
PROVIDER_PATH = f'{POOL_PATH}/providers/{PROVIDER}'
PRINCIPAL = f'principalSet://iam.googleapis.com/{POOL_PATH}/attribute.repository_id/{REPO_ID}'
MARKER = 'richon-portal-github-v1'
TAG = 'portal-candidate'
REQUEST = ROOT / '.github/portal-deploy.request'
MAPPING = {'google.subject': 'assertion.sub', **{
    'attribute.' + k: 'assertion.' + k for k in
    ('repository_id', 'repository_owner_id', 'ref', 'workflow_ref', 'event_name')}}
CONDITION = (f"assertion.repository_id == '{REPO_ID}' && "
             f"assertion.repository_owner_id == '{OWNER_ID}' && "
             f"assertion.ref == '{REF}' && assertion.workflow_ref == '{WORKFLOW}' && "
             "assertion.event_name == 'push'")
SECRET_NAMES = {'DATABASE_URL': 'richon-portal-database-url',
                'KAKAO_CLIENT_ID': 'richon-kakao-rest-api-key',
                'KAKAO_CLIENT_SECRET': 'richon-kakao-client-secret',
                'RICHON_EDGE_SECRET': 'richon-portal-edge-secret'}
FLAGS = ('RICHON_EDGE_ENABLED', 'RICHON_AUTH_ENABLED',
         'RICHON_OAUTH_ENABLED', 'RICHON_PORTAL_ENABLED')
INTERNAL = {**{k: 'true' for k in FLAGS},
            'RICHON_TERMS_VERSION': 'internal-test-v1',
            'RICHON_PRIVACY_VERSION': 'internal-test-v1',
            'RICHON_TERMS_URL': 'https://richonacademy.com/terms.html',
            'RICHON_PRIVACY_URL': 'https://richonacademy.com/privacy.html'}
PLAIN = {'RICHON_BOOTSTRAP_VERIFY': 'true', 'KAKAO_APP_ID': '1585992',
         'RICHON_OAUTH_ORIGIN': 'https://richonacademy.com',
         'RICHON_AUTH_ALLOWED_ORIGINS': 'https://richonacademy.com',
         'RICHON_MONTHLY_ENABLED': 'false', 'RICHON_MANUAL_ENABLED': 'false'}


class Stop(Exception):
    """A fixed code only. Never attach raw stdout/stderr or exception text."""


def need(condition, code):
    if not condition:
        raise Stop(code)


def error_code(raw):
    text = raw.decode('utf-8', errors='replace').lower()
    for code, markers in (
        ('auth_required', ('active account', 'invalid_grant', 'unauthenticated', 'reauthentication', 'gcloud auth login')),
        ('permission_denied', ('permission_denied', 'permission denied', 'does not have permission', 'forbidden')),
        ('resource_missing', ('not_found', 'not found', 'does not exist')),
        ('network_error', ('connectionerror', 'connection timed out', 'service unavailable')),
        ('cli_argument_error', ('unrecognized arguments', 'invalid choice')),
    ):
        if any(x in text for x in markers):
            return code
    return 'command_failed'


def command(args, *, timeout=120):
    env = dict(os.environ, CLOUDSDK_CORE_LOG_HTTP='false',
               CLOUDSDK_CORE_VERBOSITY='error', CLOUDSDK_CORE_DISABLE_USAGE_REPORTING='true')
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise Stop('command_timeout') from None
    except OSError:
        raise Stop('command_unavailable') from None
    if result.returncode:
        raise Stop(error_code(result.stderr))
    return result.stdout.decode('utf-8')


def gc(*args, timeout=120):
    text = command(['gcloud', *args, '--project=' + PROJECT, '--quiet', '--format=json'], timeout=timeout)
    try:
        return json.loads(text) if text.strip() else None
    except (ValueError, UnicodeError):
        raise Stop('invalid_cloud_response') from None


def source(*, live=False):
    sha = command(['git', 'rev-parse', 'HEAD']).strip()
    need(re.fullmatch('[a-f0-9]{40}', sha), 'invalid_source_sha')
    need(not command(['git', 'status', '--porcelain', '--untracked-files=all']).strip(), 'dirty_checkout')
    command(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'])
    if live:
        expected = {'GITHUB_REPOSITORY': REPO, 'GITHUB_REPOSITORY_ID': REPO_ID,
                    'GITHUB_REPOSITORY_OWNER_ID': OWNER_ID, 'GITHUB_REF': REF,
                    'GITHUB_WORKFLOW_REF': WORKFLOW, 'GITHUB_EVENT_NAME': 'push', 'GITHUB_SHA': sha}
        need(all(os.getenv(k) == v for k, v in expected.items()), 'untrusted_workflow_context')
        remote = command(['git', 'ls-remote', '--exit-code', 'https://github.com/' + REPO + '.git', REF]).strip().split()
        need(remote == [sha, REF], 'stale_request_commit')
    return sha


def read_request(value=None):
    if value is None:
        need(REQUEST.stat().st_size <= 2048, 'request_too_large')
        value = json.loads(REQUEST.read_text())
    need(isinstance(value, dict) and set(value) == {'operation', 'request_id'}, 'invalid_request')
    need(value['operation'] in ('hold', 'inspect', 'deploy', 'configure-internal-login'), 'unsupported_operation')
    need(isinstance(value['request_id'], str) and re.fullmatch('[A-Za-z0-9_.-]{1,80}', value['request_id']), 'invalid_request_id')
    return value


def environment(container):
    entries = container.get('env', [])
    need(all(isinstance(e, dict) and isinstance(e.get('name'), str) for e in entries), 'invalid_env')
    result = {e['name']: e for e in entries}
    need(len(entries) == len(result), 'duplicate_env')
    return result


def private(policy, svc):
    annotations = svc.get('metadata', {}).get('annotations', {})
    need(annotations.get('run.googleapis.com/invoker-iam-disabled', 'false') == 'false', 'public_boundary_requires_separate_review')
    need(not any(m in {'allUsers', 'allAuthenticatedUsers'} for b in policy.get('bindings', [])
                 for m in b.get('members', [])), 'public_boundary_requires_separate_review')


def inspect(svc, policy, *, require_ready=True):
    meta = svc.get('metadata', {})
    need(meta.get('name') == SERVICE and str(meta.get('namespace')) == NUMBER, 'wrong_service_target')
    need(meta.get('labels', {}).get('managed-by') == 'richon-portal-bootstrap-v1', 'unmanaged_service')
    private(policy, svc)
    annotations = meta.get('annotations', {})
    template = svc.get('spec', {}).get('template', {})
    spec = template.get('spec', {})
    need(spec.get('serviceAccountName') == RUNTIME, 'wrong_runtime')
    containers = spec.get('containers', [])
    need(len(containers) == 1 and not spec.get('volumes'), 'unexpected_containers_or_volumes')
    c = containers[0]
    need(not c.get('command') and not c.get('args') and not c.get('volumeMounts'), 'entry_override_not_allowed')
    need(re.fullmatch(re.escape(IMAGE) + r'@sha256:[a-f0-9]{64}', c.get('image', '')), 'unpinned_portal_image')
    limits = c.get('resources', {}).get('limits', {})
    need(limits.get('cpu') in ('1', '1000m') and limits.get('memory') == '512Mi', 'unexpected_resources')
    need(spec.get('containerConcurrency') == 20 and spec.get('timeoutSeconds') == 60, 'unexpected_runtime_limits')
    scaling = template.get('metadata', {}).get('annotations', {})
    need(str(scaling.get('autoscaling.knative.dev/maxScale')) == '1' and
         str(scaling.get('autoscaling.knative.dev/minScale', '0')) == '0', 'revision_scaling_changed')
    need(str(annotations.get('run.googleapis.com/minScale', '0')) == '0' and
         str(annotations.get('run.googleapis.com/maxScale', '1')) == '1', 'service_scaling_changed')
    env = environment(c)
    need(set(env) <= set(SECRET_NAMES) | set(PLAIN) | set(INTERNAL), 'unreviewed_env')
    for name, secret in SECRET_NAMES.items():
        item = env.get(name, {})
        ref = item.get('valueFrom', {}).get('secretKeyRef', {})
        need('value' not in item and ref.get('name') == secret and
             re.fullmatch('[1-9][0-9]*', str(ref.get('key', ''))), 'missing_or_unpinned_secret_reference')
    need(all(env.get(k, {}).get('value') == v for k, v in PLAIN.items()), 'unexpected_portal_setting')
    modes = {env.get(k, {}).get('value') for k in FLAGS}
    need(modes in ({'false'}, {'true'}), 'partial_login_config')
    for key in set(INTERNAL) - set(FLAGS):
        need((key not in env and modes == {'false'}) or env.get(key, {}).get('value') == INTERNAL[key], 'unreviewed_consent_config')
    status = svc.get('status', {})
    need(status.get('url') == URL, 'wrong_service_url')
    for field in ('latestCreatedRevisionName', 'latestReadyRevisionName'):
        need(re.fullmatch(SERVICE + r'-[a-z0-9-]+', status.get(field, '')), 'invalid_revision_name')
    if require_ready:
        need(any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in status.get('conditions', [])), 'service_not_ready')
        need(status.get('latestCreatedRevisionName') == status.get('latestReadyRevisionName'), 'unready_revision_pending')
    return {'enabled': modes == {'true'}, 'revision': status['latestReadyRevisionName'], 'image': c['image']}


def get_service(*, require_ready=True):
    svc = gc('run', 'services', 'describe', SERVICE, '--region=' + REGION)
    policy = gc('run', 'services', 'get-iam-policy', SERVICE, '--region=' + REGION)
    inspect(svc, policy, require_ready=require_ready)
    return svc, policy


def policy_key(policy):
    # Stable despite API order or etag changes; conditions and audit config kept.
    result = deepcopy(policy)
    result.pop('etag', None)
    for binding in result.get('bindings', []):
        binding['members'] = sorted(binding.get('members', []))
    result['bindings'] = sorted(result.get('bindings', []), key=lambda b: json.dumps(b, sort_keys=True))
    return result


def protected(svc):
    result = deepcopy(svc['spec'])
    result.pop('traffic', None)
    template = result['template']
    template.get('metadata', {}).pop('name', None)
    for annotations in (template.get('metadata', {}).get('annotations', {}),):
        for key in ('run.googleapis.com/client-name', 'run.googleapis.com/client-version'):
            annotations.pop(key, None)
    container = template['spec']['containers'][0]
    container.pop('image', None)
    container['env'] = sorted(container.get('env', []), key=lambda x: x['name'])
    # Preserve all meaningful service-level annotations, including IAM/ingress.
    meta = deepcopy(svc['metadata'])
    annotations = meta.get('annotations', {})
    for key in ('run.googleapis.com/operation-id', 'run.googleapis.com/urls',
                'run.googleapis.com/client-name', 'run.googleapis.com/client-version',
                'serving.knative.dev/creator', 'serving.knative.dev/lastModifier'):
        annotations.pop(key, None)
    return {'spec': result, 'annotations': annotations, 'labels': meta.get('labels', {})}


def intended(svc, operation):
    result = deepcopy(svc)
    if operation == 'configure-internal-login':
        c = result['spec']['template']['spec']['containers'][0]
        env = environment(c)
        env.update({k: {'name': k, 'value': v} for k, v in INTERNAL.items()})
        c['env'] = list(env.values())
    return result


def traffic(svc):
    return sorted((x.get('revisionName'), int(x.get('percent', 0)))
                  for x in svc['status'].get('traffic', []) if int(x.get('percent', 0)) > 0)


def candidate_url(svc, revision):
    matches = [r for r in svc['status'].get('traffic', []) if r.get('tag') == TAG and r.get('revisionName') == revision]
    need(len(matches) == 1, 'candidate_tag_missing')
    url = matches[0].get('url', '')
    expected = 'https://' + TAG + '---' + urlsplit(URL).netloc
    need(url == expected, 'unsafe_candidate_url')
    return url
