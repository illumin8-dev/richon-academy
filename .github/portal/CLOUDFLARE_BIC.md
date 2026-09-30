# Cloudflare BIC / CHECKPOINT-023 / 2026-09-24

## Evidence and scope

The owner supplied a Cloudflare Security Events screenshot. The expanded event at 2026-09-24 10:16:28 GMT+9 is GET richonacademy.com/apply.html, query empty, service Browser Integrity Check, action Block, user agent Python-urllib/3.12. Several adjacent events at that time display the same service. The expanded event supports BIC as its blocking product; it does not reveal BIC's internal header signature or prove every unrelated 403 shares the cause. Do not call this a country/IP ban.

The timestamp/path correspond to failed deployment run35942079551 / portal job107452142060. Its six public probes were403 and it stopped before registry push/Cloud Run update. DB008 and both Naver runtime grants version1 already passed the owner's helper; do not redo them.

## Code change

Fixed explicit User-Agent: `RichonPortalDeployCheck/1.0`. This honestly identifies an automated probe; it is not Mozilla/browser impersonation, a password, or proof that a request really came from GitHub. The URL allowlist, GET-only probes, no cookies/authentication, no redirects, strict Access tenant redirect requirement and rejection of403/challenges remain unchanged. This header alone is NOT claimed to solve BIC.

## Proposed owner-side rule — NOT applied by this code

In richonacademy.com Security > Security rules > Create rule > Custom rules:

Name: `Richon deployment check - BIC only`

Expression:

```text
(http.host eq "richonacademy.com"
 and http.request.method eq "GET"
 and http.request.uri.query eq ""
 and http.user_agent eq "RichonPortalDeployCheck/1.0"
 and http.request.uri.path in {"/" "/apply.html" "/auth/login" "/auth/kakao/callback" "/auth/naver/callback" "/portal/mypage"})
```

Action: Skip. Select **Browser Integrity Check only** (API product `bic`). Leave remaining custom rules, managed rules, rate limiting, Super Bot Fight Mode, User Agent Blocking, Security Level, and other skip options unselected. Keep matching-request logging enabled. Do not add an Access Bypass policy or change its owner-email rule. Do not disable BIC globally. Do not allow all Microsoft/Azure/US IPs or Python clients.

This deliberately exempts a small request class from one heuristic check. **Anyone can copy a User-Agent; this is not an allowlist of authenticated users.** Other security products, Cloudflare Access, origin edge-key checks and application authentication still apply. It does not match POSTs, OAuth callbacks containing code/state, other paths, hosts or agents. Retain only while this diagnostic exception is needed; disabling this one rule rolls back the exception without changing global BIC or Access.

Alternative: a configuration rule with exactly the same expression and only Browser Integrity Check=Off can express the same BIC exception. Do not deploy both alternatives. A fixed runner IP/mTLS-bound exception would restrict the sender further, but no fixed egress or mTLS identity is currently configured; do not invent one or treat the screenshot IP as permanent.

## Next step

Owner reviews and applies the BIC-only rule. After confirmation, first run inspect-edge with a new request ID from the current trusted deployment branch. Check the six paths reach the expected Access login gateway/public200, not a blanket403. The Access login redirect is not proof of the owner-email policy content. Only then continue stage-edge-naver, preserve existing100% traffic, verify the exact candidate and follow the separate promotion process. If another product blocks, inspect the new event; do not broaden this rule automatically.

No Cloudflare setting, DB/IAM, provider token, service image/traffic, homepage, policy copy or PR10 was changed in this code PR. No cloud operation request file was modified. Reused existing short-lived branch; no extra branch created. CI results are recorded in the PR after execution.

## Official documentation checked separately from screenshot evidence

- https://developers.cloudflare.com/waf/tools/browser-integrity-check/
- https://developers.cloudflare.com/waf/custom-rules/skip/
- https://developers.cloudflare.com/waf/custom-rules/skip/options/
- https://developers.cloudflare.com/rules/configuration-rules/settings/
