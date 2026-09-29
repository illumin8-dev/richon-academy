"""One-time recovery for the orphaned login-handoff check tag.

This file is deliberately scoped to the interrupted workflow run 36609510020.
It may remove only the exact zero-traffic portal-handoff-check tag created by
that run. It does not change the portal-candidate tag, default traffic, IAM,
runtime configuration, secrets, database state, or feature flags.
"""
import sys

import common as c
import edge_ops as e
import login_handoff_rollout as h
import operate as op

OPERATION = 'recover-login-handoff-check'
ORPHAN_REVISION = 'richon-portal-handoff-36609510020-1'
EXPECTED_CANDIDATE = 'richon-portal-handoff-36597611986-1'


def validate_before_rows(svc):
    rows = svc.get('status', {}).get('traffic', [])
    c.need(len(rows) == 3, 'recovery_unexpected_traffic_rows')

    serving = [row for row in rows if not row.get('tag') and int(row.get('percent', 0)) == 100]
    candidate = [row for row in rows if row.get('tag') == c.TAG]
    check = [row for row in rows if row.get('tag') == h.CHECK_TAG]

    c.need(len(serving) == len(candidate) == len(check) == 1,
           'recovery_expected_rows_missing')
    c.need(candidate[0].get('revisionName') == EXPECTED_CANDIDATE
           and int(candidate[0].get('percent', 0)) == 0
           and candidate[0].get('url') == e.CANDIDATE,
           'recovery_candidate_changed')
    c.need(check[0].get('revisionName') == ORPHAN_REVISION
           and int(check[0].get('percent', 0)) == 0
           and check[0].get('url') == h.CHECK_URL,
           'recovery_orphan_check_mismatch')
    c.need(all((not row.get('tag')) or row.get('tag') in (c.TAG, h.CHECK_TAG)
               for row in rows),
           'recovery_unknown_tag_present')
    return serving[0].get('revisionName')


def rows_without_check(svc):
    return sorted(row for row in h.tag_rows(svc) if row[0] != h.CHECK_TAG)


def run():
    sha = c.source(live=True)
    request = c.read_request()
    c.need(request['operation'] == OPERATION, 'explicit_handoff_recovery_required')

    before, policy = e.get_service()
    info = c.inspect(before, policy, boundary='edge')
    c.need(info['account_enabled'] is True and info['marketing_enabled'] is True,
           'recovery_features_changed')
    serving = validate_before_rows(before)
    c.need(before['status'].get('latestCreatedRevisionName') == ORPHAN_REVISION
           and before['status'].get('latestReadyRevisionName') == ORPHAN_REVISION,
           'recovery_orphan_not_latest_ready')

    h.verify_revision(ORPHAN_REVISION, before, policy)
    h.probe_gate(h.CHECK_URL)
    c.need(e.access_status() == 'signin-gateway-confirmed',
           'recovery_access_gateway_not_confirmed')

    fresh, fresh_policy = e.get_service()
    c.need(c.protected(fresh) == c.protected(before)
           and c.policy_key(fresh_policy) == c.policy_key(policy)
           and h.tag_rows(fresh) == h.tag_rows(before)
           and fresh['status'].get('latestReadyRevisionName') == ORPHAN_REVISION,
           'recovery_state_changed_before_cleanup')
    c.source(live=True)

    c.gc('run', 'services', 'update-traffic', c.SERVICE, '--region=' + c.REGION,
         '--remove-tags=' + h.CHECK_TAG, timeout=180)

    after, after_policy = e.get_service()
    c.need(c.protected(after) == c.protected(before),
           'recovery_configuration_changed')
    c.need(c.policy_key(after_policy) == c.policy_key(policy),
           'recovery_iam_changed')
    c.need(c.traffic(after) == c.traffic(before) == [(serving, 100)],
           'recovery_default_traffic_changed')
    c.need(h.tag_rows(after) == rows_without_check(before),
           'recovery_unexpected_tags_after_cleanup')
    c.need(h.current_candidate(after) == EXPECTED_CANDIDATE,
           'recovery_candidate_changed_after_cleanup')
    c.need(not any(row.get('tag') == h.CHECK_TAG
                   for row in after.get('status', {}).get('traffic', [])),
           'recovery_check_tag_still_present')

    h.probe_gate(e.CANDIDATE)
    c.need(e.access_status() == 'signin-gateway-confirmed',
           'recovery_access_gateway_changed')

    op.summary('LOGIN HANDOFF ORPHAN CHECK RECOVERY=PASS')
    op.summary('SOURCE=' + sha + ' / REMOVED_TAG=' + h.CHECK_TAG)
    op.summary('REMOVED_REVISION_ROUTE=' + ORPHAN_REVISION + ' / CANDIDATE_UNCHANGED=' + EXPECTED_CANDIDATE)
    op.summary('DEFAULT_100_PERCENT_UNCHANGED=' + serving)
    op.summary('IAM_UNCHANGED=PASS / CONFIG_UNCHANGED=PASS / DB_AND_FEATURE_FLAGS_NOT_TOUCHED')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(run())
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, c.Stop) else 'unexpected_handoff_recovery_failure'
        print('STOP: login-handoff-recovery / ' + code + '. No raw credentials or responses printed.',
              file=sys.stderr)
        raise SystemExit(1) from None
