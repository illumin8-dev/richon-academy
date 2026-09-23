"""Owner-only prerequisites for the already-approved Kakao/Naver internal test.

No side effects on import. Does not deploy or change Cloud Run/Access/WIF.
Only 008's exact forward migration and two per-secret runtime grants can change.
Never prints DSNs, OAuth credentials, customer rows, or raw gcloud responses.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qsl

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / '.github/portal'))
sys.path.insert(0, str(ROOT / 'backend'))
import common as c
import db
import login_return_migrate as migration
import portal_readiness as ready
from prepare_portal import validate_dsn

ACCOUNT = 'richon.illumin8@gmail.com'
OWNER_SECRET = 'richon-database-url'
NAVER = ('richon-naver-client-id', 'richon-naver-client-secret')
RUNTIME_MEMBER = 'serviceAccount:' + c.RUNTIME
GRANT = 'roles/secretmanager.secretAccessor'
REPORT = {'database_008': 'not_run', 'naver_runtime_grants': [], 'server_deployed': False}


def reset_report():
    REPORT.clear()
    REPORT.update(database_008='not_run', naver_runtime_grants=[], server_deployed=False)


def checksum(version):
    return hashlib.sha256((migration.DIRECTORY / (version + '.sql')).read_bytes()).hexdigest()


def secret_version(name, preferred=None):
    c.need(name in NAVER + (OWNER_SECRET,), 'unexpected_secret_target')
    rows = c.gc('secrets', 'versions', 'list', name, '--filter=state:ENABLED')
    c.need(isinstance(rows, list), 'invalid_secret_metadata')
    versions = []
    for row in rows:
        match = re.fullmatch(r'projects/([^/]+)/secrets/([^/]+)/versions/([1-9][0-9]*)', row.get('name', ''))
        c.need(match is not None and match[1] in (c.PROJECT, c.NUMBER) and match[2] == name,
               'invalid_secret_version')
        if row.get('state') == 'ENABLED':
            versions.append(match[3])
    c.need(bool(versions), 'enabled_secret_version_required')
    if preferred is not None:
        c.need(preferred in versions, 'pinned_secret_version_not_enabled')
        return preferred
    return max(versions, key=int)


def secret_text(name, version):
    # Naver values are never needed here: only its metadata and IAM are used.
    c.need(name in (OWNER_SECRET, 'richon-portal-database-url') and
           re.fullmatch('[1-9][0-9]*', str(version)), 'unexpected_secret_payload_request')
    result = c.command(['gcloud', 'secrets', 'versions', 'access', version,
                        '--secret=' + name, '--project=' + c.PROJECT, '--quiet']).strip()
    c.need(0 < len(result) <= 8192, 'invalid_database_configuration')
    return result


def validate_database(value, role):
    target = validate_dsn(value, role)
    pairs = parse_qsl(target.query, strict_parsing=True)
    c.need(len(dict(pairs)) == len(pairs), 'duplicate_database_option')
    return target


def check_schema(url, *, require_current=False):
    with db._connect(url) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='10s'")
            cur.execute('SELECT current_database(),current_user')
            c.need(cur.fetchone() == ('neondb', 'neondb_owner'), 'wrong_database_identity')
            for version in migration.DEPENDENCIES:
                cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s', (version,))
                c.need(cur.fetchone() == (checksum(version),), 'dependency_checksum_mismatch')
            cur.execute('SELECT checksum FROM richon.schema_migrations WHERE version=%s', (migration.VERSION,))
            existing = cur.fetchone()
            c.need(existing in (None, (checksum(migration.VERSION),)), 'migration_checksum_mismatch')
            if require_current or existing is not None:
                c.need(existing is not None, 'login_migration_missing')
                ready.check_return_paths(cur)
            else:
                # This prepared update only supports the known 007 constraint.
                expected = ready.RETURN_PATHS - {'/', '/index.html', '/apply.html'}
                ready.check_return_paths(cur, expected_paths=expected)
            ready.check_role(cur)
    return existing is not None


def restricted_check(url):
    with db._connect(url) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='10s'")
            ready.check_cursor(cur)
            ready.check_return_paths(cur)


def service():
    svc = c.gc('run', 'services', 'describe', c.SERVICE, '--region=' + c.REGION)
    policy = c.gc('run', 'services', 'get-iam-policy', c.SERVICE, '--region=' + c.REGION)
    info = c.inspect(svc, policy, boundary='edge')
    c.need(c.traffic(svc) == [(info['revision'], 100)] and
           not any(row.get('tag') for row in svc['status'].get('traffic', [])),
           'candidate_or_split_requires_review')
    return svc, policy


def same_service(before, policy):
    fresh, fresh_policy = service()
    c.need(fresh['spec'] == before['spec'] and c.protected(fresh) == c.protected(before)
           and c.traffic(fresh) == c.traffic(before) and
           c.policy_key(fresh_policy) == c.policy_key(policy), 'service_changed_during_preparation')


def secret_policy(name):
    c.need(name in NAVER, 'unexpected_secret_target')
    policy = c.gc('secrets', 'get-iam-policy', name)
    c.need(not any(m in ('allUsers', 'allAuthenticatedUsers')
                   for b in policy.get('bindings', []) for m in b.get('members', [])),
           'public_secret_policy_requires_review')
    return policy


def has_grant(policy):
    return any(b.get('role') == GRANT and not b.get('condition') and
               RUNTIME_MEMBER in b.get('members', []) for b in policy.get('bindings', []))


def with_grant(policy):
    desired = deepcopy(policy)
    if not has_grant(desired):
        for binding in desired.get('bindings', []):
            if binding.get('role') == GRANT and not binding.get('condition'):
                binding['members'].append(RUNTIME_MEMBER)
                break
        else:
            desired.setdefault('bindings', []).append({'role': GRANT, 'members': [RUNTIME_MEMBER]})
    return desired


def secret_policy_key(policy):
    """Normalize only valid IAM schema metadata, never permission content.

    Empty/default policies can omit version (protobuf default 0); the first
    unconditional binding can make the API return explicit version 1.
    Conditional bindings must remain fully represented by schema version 3.
    This comparison is local to these Secret grants, not the Cloud Run guards.
    """
    result = c.policy_key(policy)
    version = result.get('version', 0)
    c.need(type(version) is int and version in (0, 1, 3), 'invalid_secret_policy_version')
    bindings = result.get('bindings', [])
    c.need(not any('_withcond_' in b.get('role', '') for b in bindings),
           'incomplete_secret_policy_conditions')
    conditional = any(b.get('condition') for b in bindings)
    c.need(not conditional or version == 3, 'incomplete_secret_policy_conditions')
    result['version'] = 3 if conditional else 1
    return result


def ensure_grant(name, before):
    c.need(name in NAVER, 'unexpected_secret_target')
    before_key = secret_policy_key(before)
    c.need(secret_policy_key(secret_policy(name)) == before_key, 'secret_policy_changed')
    expected = secret_policy_key(with_grant(before))
    added = not has_grant(before)
    if added:
        REPORT['naver_runtime_grants'].append({'secret': name, 'status': 'grant_attempted'})
        c.gc('secrets', 'add-iam-policy-binding', name, '--member=' + RUNTIME_MEMBER,
             '--role=' + GRANT, '--condition=None')
        REPORT['naver_runtime_grants'][-1]['status'] = 'write_acknowledged'
    # Retry reads only, and only when the exact old policy is still visible.
    # An unrelated change is not explained away as IAM propagation delay.
    for delay in (0, 1, 2, 4, 8):
        if delay:
            time.sleep(delay)
        after = secret_policy(name)
        after_key = secret_policy_key(after)
        if after_key == expected and has_grant(after):
            REPORT.pop('grant_readback', None)
            return added
        REPORT['grant_readback'] = {
            'secret': name, 'policy_version': after.get('version', 0),
            'runtime_binding_present': has_grant(after),
            'old_policy_still_visible': after_key == before_key,
        }
        c.need(added and after_key == before_key, 'secret_grant_unexpected_policy')
    raise c.Stop('secret_grant_readback_pending')


def run(*, apply=False, resume_grants=False):
    reset_report()
    c.need(not os.getenv('GITHUB_ACTIONS'), 'owner_shell_required')
    c.need(not os.getenv('DATABASE_URL'), 'unset_shell_database_url_first')
    os.environ.update(CLOUDSDK_CORE_ACCOUNT=ACCOUNT, CLOUDSDK_CORE_LOG_HTTP='false')
    sha = c.source()
    remote = c.command(['git', 'remote', 'get-url', 'origin']).strip()
    c.need(remote == 'https://github.com/' + c.REPO + '.git', 'wrong_source_repository')
    accounts = c.gc('auth', 'list', '--filter=status:ACTIVE')
    c.need(len(accounts) == 1 and accounts[0].get('account') == ACCOUNT, 'owner_login_required')
    project = c.gc('projects', 'describe', c.PROJECT)
    c.need(str(project.get('projectNumber')) == c.NUMBER, 'wrong_project')
    before, policy = service()
    env = c.environment(before['spec']['template']['spec']['containers'][0])
    current = c.naver_references(env, boundary='edge')
    preferred = {ref['valueFrom']['secretKeyRef']['name']: str(ref['valueFrom']['secretKeyRef']['key'])
                 for ref in current.values()}
    versions = {name: secret_version(name, preferred.get(name)) for name in NAVER}
    policies = {name: secret_policy(name) for name in NAVER}
    runtime_version = str(env['DATABASE_URL']['valueFrom']['secretKeyRef']['key'])
    owner = secret_text(OWNER_SECRET, secret_version(OWNER_SECRET))
    runtime = secret_text('richon-portal-database-url', runtime_version)
    try:
        owner_target = validate_database(owner, 'neondb_owner')
        runtime_target = validate_database(runtime, ready.ROLE)
        c.need(owner_target.hostname.replace('-pooler.', '.') == runtime_target.hostname.replace('-pooler.', '.'),
               'database_endpoint_mismatch')
        existing = check_schema(owner, require_current=True) if resume_grants else check_schema(owner)
        c.need(not resume_grants or existing, 'resume_requires_verified_008')
        print('PASS: fixed project/service/database and existing limited runtime. No customer rows read.')
        print('008 migration: ' + ('already applied and checked' if existing else 'needs forward update'))
        print('Naver: both existing secrets have enabled versions. Values were NOT read.')
        REPORT['database_008'] = 'verified_existing' if existing else 'not_applied'
        if existing:
            restricted_check(runtime)
        if not apply:
            print('READ CHECKS PASSED. No writes. Re-run with --apply for the printed prerequisites.')
            return 0
        if resume_grants:
            print('Resume: DB008 is read-verified only. No migration/DDL will run; only missing Naver runtime grants.')
        else:
            print('Changes: only missing 008 return-path constraints and per-secret read access for richon-portal runtime.')
        print('No new secrets/passwords/roles, no project-wide permissions, no WIF/Access, no server deployment.')
        if input('Type PREPARE LOGIN to apply these prerequisites: ').strip() != 'PREPARE LOGIN':
            print('Cancelled; no writes.')
            return 0
        c.need(c.source() == sha, 'source_changed')
        same_service(before, policy)
        for name in NAVER:
            c.need(secret_version(name, preferred.get(name)) == versions[name] and secret_policy_key(secret_policy(name)) == secret_policy_key(policies[name]),
                   'naver_metadata_changed')
        check_schema(owner)
        if not resume_grants:
            REPORT['database_008'] = 'apply_attempted'
            migration.apply_migration(connection_url=owner)
        check_schema(owner, require_current=True)
        restricted_check(runtime)
        REPORT['database_008'] = 'verified_existing' if resume_grants else 'verified'
        for name in NAVER:
            added = ensure_grant(name, policies[name])
            REPORT['naver_runtime_grants'] = [r for r in REPORT['naver_runtime_grants'] if r['secret'] != name]
            REPORT['naver_runtime_grants'].append({'secret': name, 'status': 'verified', 'added': added, 'version': versions[name]})
        same_service(before, policy)
        REPORT['source_sha'] = sha
        REPORT['naver_versions'] = versions
        print('LOGIN PREREQUISITES READY')
        print(json.dumps(REPORT, sort_keys=True))
        return 0
    finally:
        del owner, runtime


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Owner-only database/Naver prerequisites; does not deploy.')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume-grants', action='store_true',
                        help='Require existing valid 008, read-check DB only, and resume Naver IAM grants.')
    args = parser.parse_args()
    try:
        raise SystemExit(run(apply=args.apply, resume_grants=args.resume_grants))
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, c.Stop) else 'prerequisite_check_failed'
        print('STOP: login prerequisites / ' + code + '. No raw credentials or errors printed.', file=sys.stderr)
        print(json.dumps(REPORT, sort_keys=True))
        raise SystemExit(1) from None
