# Edge-gated deployment preparation / 2026-09-24

## Scope
User approved starting the previously described deployment-guard correction immediately. This PR recognizes only the already approved `allUsers:roles/run.invoker` + application edge-secret mode for the existing richon-portal. It does not add new public access, secret access, Naver enablement, database changes, or customer traffic promotion.

Base: c82ea51162ff71599eeef74c380f223ed47224a4 / feat/backend-portal-deploy.
Design PR #16 remains separate. Do not repeat provider resource downloads.

## Implemented
- Legacy inspect/deploy/configure operations remain IAM-private and still reject public invocation.
- Explicit inspect-edge validates fixed service/project, public grant, enabled application gate, pinned secret references, runtime identity, image and resource limits; tests both missing/wrong keys against the actual endpoint.
- Cloudflare gateway visibility is reported separately. Generic HTTP 403 is inconclusive, never proof of the intended email policy.
- Explicit stage-edge can upload a verified image as a zero-traffic tagged revision after fresh metadata and gateway checks. No automatic promotion exists in this mode. Existing serving traffic and complete IAM policy must remain unchanged.
- No raw secret values, cookies, OAuth codes, arbitrary response bodies or full redirects are printed.
- The workflow remains bound to the existing repository/branch/workflow WIF trust and explicit request file. PR/code changes alone do not request a cloud operation.

## Local checkpoint
79 offline automation tests passed (existing 60 + new 19). CI and real inspection results must be appended to the PR after execution; do not infer them from this note.

## Observed blocker
Neon describe_project was attempted again and returned `project_id` required while its exposed schema accepts no project_id argument. No SQL was executed. Migration 008 state remains unknown; do not claim applied or bypass it with a customer traffic promotion.

## Resume
1. Read this PR head/CI; merge only reviewed guard changes into the dedicated deploy branch.
2. Request inspect-edge and record actual Cloud Run revision, origin gate result and Access gateway evidence.
3. Keep stage-edge unrequested unless preflight passes and candidate creation is appropriate. Promotion, 008 migration and Naver binding remain separate gated actions. On interrupted staging, read actual revision/traffic first; existing candidates fail closed rather than overwrite blindly.
4. Record outcomes as a PR checkpoint before returning to the user.
