"""Metadata-only deployment guards. Never print service JSON or secret values."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

PROJECT = "richon-academy"
PROJECT_NUMBER = "756298505437"
REGION = "asia-southeast1"
SERVICE = "richon-backend-test"
RUNTIME = f"richon-backend@{PROJECT}.iam.gserviceaccount.com"
SERVICE_URL = "https://richon-backend-test-amjmgyepbq-as.a.run.app"
IMAGE_BASE = f"{REGION}-docker.pkg.dev/{PROJECT}/richon-backend-ci/backend"


def require(condition, code):
    if not condition:
        raise ValueError(code)


def inspect_service(service, policy, revision=None, digest=None):
    """Fail closed on unexpected target, auth, runtime or DB secret binding."""
    metadata = service.get("metadata", {})
    require(metadata.get("name") == SERVICE, "wrong_service")
    require(str(metadata.get("namespace")) == PROJECT_NUMBER, "wrong_project")
    annotations = metadata.get("annotations", {})
    require(annotations.get("run.googleapis.com/invoker-iam-disabled", "false") == "false", "iam_check_disabled")
    require(not any(member in {"allUsers", "allAuthenticatedUsers"}
                    for binding in policy.get("bindings", [])
                    for member in binding.get("members", [])), "broad_invocation_binding")
    template = service.get("spec", {}).get("template", {})
    spec = template.get("spec", {})
    require(spec.get("serviceAccountName") == RUNTIME, "wrong_runtime_identity")
    containers = spec.get("containers", [])
    require(len(containers) == 1, "unexpected_container_count")
    env = containers[0].get("env", [])
    database = [item for item in env if item.get("name") == "DATABASE_URL"]
    require(len(database) == 1 and "value" not in database[0], "database_secret_not_referenced")
    ref = database[0].get("valueFrom", {}).get("secretKeyRef", {})
    require(ref.get("name") == "richon-database-url", "wrong_database_secret")
    require(bool(re.fullmatch(r"[1-9][0-9]*", str(ref.get("key", "")))), "secret_version_not_pinned")
    scaling = template.get("metadata", {}).get("annotations", {})
    require(str(scaling.get("autoscaling.knative.dev/maxScale")) == "1", "revision_max_scale_changed")
    require(str(scaling.get("autoscaling.knative.dev/minScale", "0")) == "0", "revision_min_scale_changed")
    require(str(annotations.get("run.googleapis.com/minScale", "0")) == "0", "service_min_scale_changed")
    require(str(annotations.get("run.googleapis.com/maxScale", "1")) == "1", "service_max_scale_changed")
    status = service.get("status", {})
    require(status.get("url") == SERVICE_URL, "unexpected_service_url")
    result = {"service_url": SERVICE_URL}
    if revision is not None:
        require(bool(re.fullmatch(SERVICE + r"-ci-[0-9]+-[0-9]+", revision)), "invalid_revision")
        require(status.get("latestReadyRevisionName") == revision, "candidate_not_ready")
        require(status.get("latestCreatedRevisionName") == revision, "concurrent_revision_change")
        require(bool(re.fullmatch(re.escape(IMAGE_BASE) + r"@sha256:[a-f0-9]{64}", digest or "")), "invalid_digest")
        require(containers[0].get("image") == digest, "candidate_image_changed")
        candidates = [row for row in status.get("traffic", [])
                      if row.get("tag") == "ci-candidate" and row.get("revisionName") == revision]
        require(len(candidates) == 1, "candidate_tag_missing")
        candidate_url = candidates[0].get("url", "")
        # Never send an ID token to an untrusted host or a redirect target.
        parsed = urlsplit(candidate_url)
        base = urlsplit(SERVICE_URL)
        require(parsed.scheme == "https" and parsed.netloc == "ci-candidate---" + base.netloc
                and parsed.path == "" and not parsed.query and not parsed.fragment, "unsafe_candidate_url")
        result.update(candidate_url=candidate_url, revision=revision)
    return result


def main():
    try:
        service = json.loads(Path(sys.argv[1]).read_text())
        policy = json.loads(Path(sys.argv[2]).read_text())
        result = inspect_service(service, policy, *sys.argv[3:])
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        print("FAIL: deployment metadata guard rejected the configuration.", file=sys.stderr)
        return 1
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
