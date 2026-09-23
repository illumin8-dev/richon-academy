"""Read-only diagnosis of bootstrap command failures; never calls setup().
No credentials are read, no SQL is executed and no cloud resources are changed.
Only fixed step names and fixed result codes are printed, not command output.
Run with Python 3 from a clean checkout; no additional packages are needed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'richon-academy'
REGION = 'asia-southeast1'
BASE = '49bf0346e834a929f5072c5bf2b99d40237fe936'


def cloud(*args):
    return ('gcloud', *args, '--project=' + PROJECT, '--quiet', '--format=json')


# Closed allowlist: no access/print-token, IAM writes, SQL, builds or deploys.
CHECKS = {
    'source-status': ('git', 'status', '--porcelain', '--untracked-files=all'),
    'source-history': ('git', 'merge-base', '--is-ancestor', BASE, 'HEAD'),
    'active-account': cloud('auth', 'list', '--filter=status:ACTIVE'),
    'project-metadata': cloud('projects', 'describe', PROJECT),
    'existing-service': cloud('run', 'services', 'describe', 'richon-backend-test', '--region=' + REGION),
    'existing-service-iam': cloud('run', 'services', 'get-iam-policy', 'richon-backend-test', '--region=' + REGION),
    'build-identity': cloud('iam', 'service-accounts', 'describe', 'richon-build@richon-academy.iam.gserviceaccount.com'),
    'project-iam': cloud('projects', 'get-iam-policy', PROJECT),
    'service-list': cloud('run', 'services', 'list', '--region=' + REGION),
    'portal-service': cloud('run', 'services', 'describe', 'richon-portal', '--region=' + REGION),
    'portal-service-iam': cloud('run', 'services', 'get-iam-policy', 'richon-portal', '--region=' + REGION),
    'kakao-key-versions': cloud('secrets', 'versions', 'list', 'richon-kakao-rest-api-key', '--filter=state:ENABLED'),
    'kakao-secret-versions': cloud('secrets', 'versions', 'list', 'richon-kakao-client-secret', '--filter=state:ENABLED'),
}


class CheckFailed(Exception):
    """Contains only a fixed code, never stdout/stderr or command arguments."""


def error_hint(stderr):
    text = (stderr or b'').decode('utf-8', errors='replace').lower()
    groups = (
        ('authorization_required', ('reauthentication', 're-authentication', 'refresh your current auth tokens',
                                    'invalid_grant', 'unauthenticated', 'gcloud auth login', 'authorize cloud shell',
                                    'do not currently have an active account', 'credentials have expired')),
        ('api_not_enabled', ('service_disabled', 'accessnotconfigured', 'api has not been used', 'api is disabled')),
        ('permission_denied', ('permission_denied', 'permission denied', 'does not have permission', 'forbidden')),
        ('resource_not_found', ('not_found', 'not found', 'does not exist')),
        ('network_or_service_error', ('connectionerror', 'connection refused', 'failed to establish',
                                      'name resolution', 'connection timed out', 'service unavailable')),
        ('invalid_cli_arguments', ('unrecognized arguments', 'invalid choice', 'invalid argument')),
    )
    for code, markers in groups:
        if any(marker in text for marker in markers):
            return code
    return 'unclassified_error'


def read(step):
    # Caller cannot supply a shell command or arbitrary command arguments.
    args = CHECKS[step]
    env = dict(os.environ, CLOUDSDK_CORE_LOG_HTTP='false', CLOUDSDK_CORE_VERBOSITY='error')
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=90, check=False)
    except subprocess.TimeoutExpired:
        raise CheckFailed('command_timeout') from None
    except OSError:
        raise CheckFailed('command_could_not_start') from None
    if result.returncode:
        raise CheckFailed(error_hint(result.stderr))
    if args[0] == 'git':
        if step == 'source-status' and result.stdout.strip():
            raise CheckFailed('clean_checkout_required')
        value = None
    else:
        try:
            value = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            raise CheckFailed('invalid_response') from None
        expected = list if step in {'active-account', 'service-list', 'kakao-key-versions', 'kakao-secret-versions'} else dict
        if not isinstance(value, expected):
            raise CheckFailed('invalid_response')
        if step == 'active-account' and not value:
            raise CheckFailed('no_active_account')
        if step == 'project-metadata' and str(value.get('projectNumber')) != '756298505437':
            raise CheckFailed('wrong_project')
        if step in {'kakao-key-versions', 'kakao-secret-versions'} and not value:
            raise CheckFailed('no_enabled_secret_version')
    return value


def main():
    step = 'source-status'
    try:
        sequence = ['source-status', 'source-history', 'active-account', 'project-metadata',
                    'existing-service', 'existing-service-iam', 'build-identity', 'project-iam', 'service-list']
        for step in sequence:
            value = read(step)
            print('PASS: ' + step, flush=True)
        if any(isinstance(row, dict) and isinstance(row.get('metadata'), dict)
               and row['metadata'].get('name') == 'richon-portal' for row in value):
            for step in ('portal-service', 'portal-service-iam'):
                read(step)
                print('PASS: ' + step, flush=True)
        for step in ('kakao-key-versions', 'kakao-secret-versions'):
            read(step)
            print('PASS: ' + step, flush=True)
    except CheckFailed as exc:
        print('CHECK FAILED: ' + step + ' / ' + str(exc), file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print('CHECK FAILED: ' + step + ' / diagnostic_interrupted', file=sys.stderr)
        return 1
    print('PREFLIGHT READ CHECKS PASSED. Setup was NOT run.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
