"""No redirects, no response-body logging, and no customer/order writes."""
import json
import os
import urllib.error
import urllib.request
from guard import SERVICE_URL, require


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    url = os.environ.get("CANDIDATE_URL", "")
    expected = SERVICE_URL.replace("https://", "https://ci-candidate---", 1)
    require(url == expected, "unsafe_probe_url")
    token = os.environ.get("TEST_ID_TOKEN", "")
    require(bool(token), "missing_identity_token")
    opener = urllib.request.build_opener(NoRedirect())
    try:
        opener.open(url + "/health", timeout=30).close()
    except urllib.error.HTTPError as response:
        require(response.code in {401, 403}, "unexpected_anonymous_status")
    else:
        raise ValueError("anonymous_access_not_blocked")
    for path, expected_body in (("/health", {"status": "ok"}),
                                ("/health/db", {"status": "ok", "database": "reachable"})):
        request = urllib.request.Request(url + path, headers={"Authorization": "Bearer " + token})
        with opener.open(request, timeout=40) as response:
            require(response.status == 200, "health_status_failed")
            require(response.headers.get("Cache-Control") == "no-store", "cache_policy_failed")
            require(json.loads(response.read(4096)) == expected_body, "health_body_failed")
    print("PASS: candidate requires IAM authentication; process and read-only DB checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError):
        # Do not print tokens, URLs from exceptions, or server response bodies.
        print("FAIL: private candidate health checks failed; previous service traffic is unchanged.")
        raise SystemExit(1)
