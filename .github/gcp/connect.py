#!/usr/bin/env python3
"""One-time owner-approved WIF setup; no keys, DB reads, or deployments."""
import json
import shutil
import subprocess
import sys
import time

from guard import PROJECT, PROJECT_NUMBER, REGION, RUNTIME, SERVICE, inspect_service

REPOSITORY = "illumin8-dev/richon-academy"
REPOSITORY_ID = "1380040761"
OWNER_ID = "251193658"
BRANCH = "refs/heads/feat/backend-gcp-deploy"
WORKFLOW = f"{REPOSITORY}/.github/workflows/backend-deploy-test.yml@{BRANCH}"
POOL = "richon-github-test"
PROVIDER = "github-test"
DEPLOYER = f"richon-github-deploy@{PROJECT}.iam.gserviceaccount.com"
REGISTRY = "richon-backend-ci"
POOL_PATH = f"projects/{PROJECT_NUMBER}/locations/global/workloadIdentityPools/{POOL}"
PROVIDER_PATH = f"{POOL_PATH}/providers/{PROVIDER}"
PRINCIPAL = f"principalSet://iam.googleapis.com/{POOL_PATH}/attribute.repository_id/{REPOSITORY_ID}"
MAPPING = {
    "google.subject": "assertion.sub",
    **{f"attribute.{name}": f"assertion.{name}" for name in
       ("repository_id", "repository_owner_id", "ref", "workflow_ref", "event_name")},
}
CONDITION = (f"assertion.repository_id == '{REPOSITORY_ID}' && "
             f"assertion.repository_owner_id == '{OWNER_ID}' && "
             f"assertion.ref == '{BRANCH}' && "
             f"assertion.workflow_ref == '{WORKFLOW}' && assertion.event_name == 'push'")


def gcloud(*args, attempts=1):
    """Only metadata/resource-policy operations. Do not call with secret payloads."""
    for attempt in range(attempts):
        proc = subprocess.run(["gcloud", *args, f"--project={PROJECT}", "--quiet", "--format=json"],
                              text=True, capture_output=True, timeout=300)
        if proc.returncode == 0:
            return json.loads(proc.stdout) if proc.stdout.strip() else None
        if attempt + 1 < attempts:
            print("Waiting for IAM propagation...", flush=True)
            time.sleep(min(5 * (2 ** attempt), 30))
    # No credential material is passed to these commands; still keep stdout private.
    print(proc.stderr[-2000:], file=sys.stderr)
    raise RuntimeError("gcloud_operation_failed")


def provider_is_expected(provider):
    return (provider.get("attributeMapping") == MAPPING
            and provider.get("attributeCondition") == CONDITION
            and provider.get("oidc", {}).get("issuerUri") == "https://token.actions.githubusercontent.com"
            and not provider.get("oidc", {}).get("allowedAudiences"))


def ensure_binding(prefix, member, role, **options):
    gcloud(*prefix, "add-iam-policy-binding", options.pop("resource"),
           *options.pop("extra", []), f"--member={member}", f"--role={role}",
           "--condition=None", attempts=6)
    policy = gcloud(*prefix, "get-iam-policy", options.pop("check_resource"),
                    *options.pop("check_extra", []))
    if not any(b.get("role") == role and not b.get("condition") and member in b.get("members", [])
               for b in policy.get("bindings", [])):
        raise RuntimeError("policy_readback_failed")


def main():
    if shutil.which("gcloud") is None:
        raise RuntimeError("Run this from the authenticated Google Cloud Shell")
    project = gcloud("projects", "describe", PROJECT)
    if str(project.get("projectNumber")) != PROJECT_NUMBER:
        raise RuntimeError("wrong_project_number")
    service = gcloud("run", "services", "describe", SERVICE, f"--region={REGION}")
    policy = gcloud("run", "services", "get-iam-policy", SERVICE, f"--region={REGION}")
    inspect_service(service, policy)
    print(f"Project: {PROJECT} / target: {SERVICE}")
    print(f"Trust ONLY {REPOSITORY} / {BRANCH} / backend-deploy-test.yml / push")
    print("Grants: deploy+invoke on that service, write to one image repository,")
    print("actAs on its runtime identity, service usage, and short-lived WIF credentials.")
    print("No Owner/Editor, no service account keys, no Secret Accessor for the deployer.")
    print("Trusted deploy code CAN use the runtime's existing DB access. Protect this branch.")
    print("This setup does not deploy, expose the service, change DB data, or edit the website.")
    if input("Connect GitHub to this TEST service? Type CONNECT: ").strip() != "CONNECT":
        print("Cancelled; no changes made.")
        return 0
    gcloud("services", "enable", "iam.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com")
    accounts = gcloud("iam", "service-accounts", "list")
    existing = [x for x in accounts if x.get("email") == DEPLOYER]
    if not existing:
        gcloud("iam", "service-accounts", "create", "richon-github-deploy",
               "--display-name=Richon test GitHub deployer")
    account = gcloud("iam", "service-accounts", "describe", DEPLOYER, attempts=6)
    if account.get("disabled"):
        raise RuntimeError("deployer_disabled_no_changes_to_enable_it")
    repos = gcloud("artifacts", "repositories", "list", f"--location={REGION}")
    existing = [x for x in repos if x.get("name", "").endswith("/" + REGISTRY)]
    if not existing:
        gcloud("artifacts", "repositories", "create", REGISTRY, f"--location={REGION}",
               "--repository-format=docker", "--description=Richon GitHub test images only")
    registry = gcloud("artifacts", "repositories", "describe", REGISTRY, f"--location={REGION}")
    if registry.get("format") != "DOCKER" or registry.get("mode", "STANDARD_REPOSITORY") != "STANDARD_REPOSITORY":
        raise RuntimeError("unexpected_registry_type")
    pools = gcloud("iam", "workload-identity-pools", "list", "--location=global")
    existing = [x for x in pools if x.get("name") == POOL_PATH]
    if not existing:
        gcloud("iam", "workload-identity-pools", "create", POOL, "--location=global",
               "--display-name=Richon GitHub test only")
    pool = gcloud("iam", "workload-identity-pools", "describe", POOL, "--location=global")
    if pool.get("state") != "ACTIVE" or pool.get("disabled"):
        raise RuntimeError("pool_not_active_do_not_override_revocation")
    provider_flags = ["--location=global", f"--workload-identity-pool={POOL}"]
    providers = gcloud("iam", "workload-identity-pools", "providers", "list", *provider_flags)
    if any(x.get("name") != PROVIDER_PATH for x in providers):
        raise RuntimeError("dedicated_pool_contains_unexpected_provider")
    existing = [x for x in providers if x.get("name") == PROVIDER_PATH]
    if not existing:
        gcloud("iam", "workload-identity-pools", "providers", "create-oidc", PROVIDER,
               *provider_flags, "--issuer-uri=https://token.actions.githubusercontent.com",
               "--attribute-mapping=" + ",".join(f"{k}={v}" for k, v in MAPPING.items()),
               "--attribute-condition=" + CONDITION)
    provider = gcloud("iam", "workload-identity-pools", "providers", "describe", PROVIDER, *provider_flags)
    if not provider_is_expected(provider) or provider.get("disabled") or provider.get("state") != "ACTIVE":
        raise RuntimeError("provider_mismatch_do_not_broaden_or_reenable")
    member = f"serviceAccount:{DEPLOYER}"
    for role in ("roles/run.developer", "roles/run.invoker"):
        ensure_binding(["run", "services"], member, role, resource=SERVICE, check_resource=SERVICE,
                       extra=[f"--region={REGION}"], check_extra=[f"--region={REGION}"])
    ensure_binding(["artifacts", "repositories"], member, "roles/artifactregistry.writer",
                   resource=REGISTRY, check_resource=REGISTRY,
                   extra=[f"--location={REGION}"], check_extra=[f"--location={REGION}"])
    ensure_binding(["iam", "service-accounts"], member, "roles/iam.serviceAccountUser",
                   resource=RUNTIME, check_resource=RUNTIME)
    ensure_binding(["projects"], member, "roles/serviceusage.serviceUsageConsumer",
                   resource=PROJECT, check_resource=PROJECT)
    # Establish impersonation only AFTER least-privilege resource grants are ready.
    ensure_binding(["iam", "service-accounts"], PRINCIPAL, "roles/iam.workloadIdentityUser",
                   resource=DEPLOYER, check_resource=DEPLOYER)
    print("SETUP READY: GitHub test-deploy permissions saved and read back.")
    print("GitHub OIDC authentication and deployment still need a real workflow run.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError, EOFError) as exc:
        print(f"FAIL: {type(exc).__name__}; connection setup not confirmed.", file=sys.stderr)
        raise SystemExit(1)
