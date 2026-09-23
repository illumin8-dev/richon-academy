#!/usr/bin/env python3
"""Owner-run one-time WIF grants; no deployment, secret reads, SQL or public IAM."""
import sys
import time
import common as c

STAGE = 'preflight'


def provider_matches(value):
    return (value.get('attributeMapping') == c.MAPPING and value.get('attributeCondition') == c.CONDITION
            and value.get('oidc', {}).get('issuerUri') == 'https://token.actions.githubusercontent.com'
            and not value.get('oidc', {}).get('allowedAudiences'))


def member_grants(policy, member, allowed):
    for b in policy.get('bindings', []):
        if member in b.get('members', []):
            c.need(b.get('role') in allowed and not b.get('condition'), 'unexpected_existing_deployer_grant')


def bind(prefix, resource, member, role, extra=()):
    # Additive single-member grants. Never replace an entire IAM policy.
    for attempt in range(6):
        try:
            c.gc(*prefix, 'add-iam-policy-binding', resource, *extra,
                 '--member=' + member, '--role=' + role, '--condition=None')
            policy = c.gc(*prefix, 'get-iam-policy', resource, *extra)
            c.need(any(b.get('role') == role and not b.get('condition') and
                       member in b.get('members', []) for b in policy.get('bindings', [])), 'iam_readback_failed')
            return
        except c.Stop:
            if attempt == 5:
                raise
            print('Waiting for IAM propagation...', flush=True)
            time.sleep(5)


def old_connection():
    # Readback proves the established order service/WIF have not been changed by this setup.
    return [
        c.gc('run', 'services', 'describe', 'richon-backend-test', '--region=' + c.REGION)['spec'],
        c.policy_key(c.gc('run', 'services', 'get-iam-policy', 'richon-backend-test', '--region=' + c.REGION)),
        c.gc('iam', 'workload-identity-pools', 'providers', 'describe', 'github-test',
             '--workload-identity-pool=richon-github-test', '--location=global'),
    ]


def setup():
    global STAGE
    c.source()
    active = c.gc('auth', 'list', '--filter=status:ACTIVE')
    c.need(isinstance(active, list) and active, 'auth_required')
    c.need(str(c.gc('projects', 'describe', c.PROJECT).get('projectNumber')) == c.NUMBER, 'wrong_project')
    svc, policy = c.get_service()
    previous = old_connection()
    project_policy = c.gc('projects', 'get-iam-policy', c.PROJECT)
    c.private(project_policy, {})
    member = 'serviceAccount:' + c.DEPLOYER
    member_grants(project_policy, member, {'roles/serviceusage.serviceUsageConsumer'})
    member_grants(policy, member, {'roles/run.developer', 'roles/run.invoker'})
    registry = c.gc('artifacts', 'repositories', 'describe', c.REGISTRY, '--location=' + c.REGION)
    c.need(registry.get('format') == 'DOCKER' and
           registry.get('labels', {}).get('managed-by') == 'richon-portal-bootstrap-v1', 'unexpected_registry')
    registry_policy = c.gc('artifacts', 'repositories', 'get-iam-policy', c.REGISTRY, '--location=' + c.REGION)
    member_grants(registry_policy, member, {'roles/artifactregistry.writer'})
    runtime_policy = c.gc('iam', 'service-accounts', 'get-iam-policy', c.RUNTIME)
    member_grants(runtime_policy, member, {'roles/iam.serviceAccountUser'})
    print('Project: richon-academy / ONLY existing service: richon-portal')
    print('Trust ONLY illumin8-dev/richon-academy / feat/backend-portal-deploy / portal-deploy.yml / push')
    print('Adds a dedicated short-lived GitHub identity, service deploy+invoke, one image repository,')
    print('actAs on richon-portal runtime, and service usage. No Owner/Editor or account keys.')
    print('No direct Secret Accessor, public IAM, DB migrations, Cloudflare or old order-server changes.')
    print('Trusted deploy code can still use runtime DB/secret access. Protect the named branch.')
    print('This command only connects permissions. Builds/runtime usage may cost money when requested later.')
    if input('Type CONNECT PORTAL to connect these permissions: ').strip() != 'CONNECT PORTAL':
        print('Cancelled. No changes made.')
        return 0
    STAGE = 'required-apis'
    c.gc('services', 'enable', 'iam.googleapis.com', 'iamcredentials.googleapis.com', 'sts.googleapis.com')
    STAGE = 'deployer-identity'
    accounts = c.gc('iam', 'service-accounts', 'list')
    matches = [a for a in accounts if a.get('email') == c.DEPLOYER]
    if not matches:
        c.gc('iam', 'service-accounts', 'create', 'richon-portal-deploy',
             '--display-name=Richon portal GitHub deployer', '--description=' + c.MARKER)
    else:
        c.need(len(matches) == 1 and matches[0].get('description') == c.MARKER
               and not matches[0].get('disabled'), 'unmanaged_or_disabled_deployer')
    STAGE = 'dedicated-pool'
    flags = ['--location=global']
    pools = c.gc('iam', 'workload-identity-pools', 'list', *flags, '--show-deleted')
    match = next((p for p in pools if p.get('name') == c.POOL_PATH), None)
    if match is None:
        c.gc('iam', 'workload-identity-pools', 'create', c.POOL, *flags,
             '--display-name=Richon portal GitHub', '--description=' + c.MARKER)
        match = c.gc('iam', 'workload-identity-pools', 'describe', c.POOL, *flags)
    c.need(match.get('description') == c.MARKER and match.get('state') == 'ACTIVE' and not match.get('disabled'), 'unexpected_or_disabled_pool')
    flags.append('--workload-identity-pool=' + c.POOL)
    values = c.gc('iam', 'workload-identity-pools', 'providers', 'list', *flags, '--show-deleted')
    c.need(all(p.get('name') == c.PROVIDER_PATH for p in values), 'unexpected_pool_provider')
    if not values:
        c.gc('iam', 'workload-identity-pools', 'providers', 'create-oidc', c.PROVIDER, *flags,
             '--issuer-uri=https://token.actions.githubusercontent.com',
             '--attribute-mapping=' + ','.join(k + '=' + v for k, v in c.MAPPING.items()),
             '--attribute-condition=' + c.CONDITION)
    value = c.gc('iam', 'workload-identity-pools', 'providers', 'describe', c.PROVIDER, *flags)
    c.need(provider_matches(value) and value.get('state') == 'ACTIVE' and not value.get('disabled'), 'unexpected_or_disabled_provider')
    STAGE = 'scoped-resource-grants'
    for role in ('roles/run.developer', 'roles/run.invoker'):
        bind(['run', 'services'], c.SERVICE, member, role, ['--region=' + c.REGION])
    bind(['artifacts', 'repositories'], c.REGISTRY, member, 'roles/artifactregistry.writer', ['--location=' + c.REGION])
    bind(['iam', 'service-accounts'], c.RUNTIME, member, 'roles/iam.serviceAccountUser')
    bind(['projects'], c.PROJECT, member, 'roles/serviceusage.serviceUsageConsumer')
    STAGE = 'federation-trust'
    policy_deployer = c.gc('iam', 'service-accounts', 'get-iam-policy', c.DEPLOYER)
    # Do not adopt a deployer that already trusts other external principals.
    for binding in policy_deployer.get('bindings', []):
        c.need(binding.get('role') == 'roles/iam.workloadIdentityUser' and not binding.get('condition')
               and set(binding.get('members', [])) <= {c.PRINCIPAL}, 'unexpected_deployer_trust')
    bind(['iam', 'service-accounts'], c.DEPLOYER, c.PRINCIPAL, 'roles/iam.workloadIdentityUser')
    STAGE = 'final-readback'
    after, after_policy = c.get_service()
    c.need(after['spec'] == svc['spec'], 'portal_changed_during_connection')
    c.need(old_connection() == previous, 'order_connection_changed_externally')
    value = c.gc('iam', 'workload-identity-pools', 'providers', 'describe', c.PROVIDER, *flags)
    c.need(provider_matches(value), 'provider_readback_failed')
    print('PORTAL AUTOMATION CONNECTED')
    print('Permission readback complete. Real GitHub authentication still needs the first inspect run.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(setup())
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, c.Stop) else 'unexpected_failure'
        print('STOP: ' + STAGE + ' / ' + code + '. Do not paste secrets.', file=sys.stderr)
        raise SystemExit(1) from None
