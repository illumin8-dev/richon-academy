"""Offline guards for DB010-compatible zero-traffic account code staging."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import account_stage as a
import candidate_readback as r
import common as c
import edge_ops as e
from test_candidate_readback import fixture


def staged_fixture():
    before, policy, _ = fixture()
    revision = c.SERVICE + '-acct-123-1'
    image = c.IMAGE + '@sha256:' + 'd' * 64
    current = deepcopy(before)
    current['spec']['template']['spec']['containers'][0]['image'] = image
    current['status']['latestCreatedRevisionName'] = revision
    current['status']['latestReadyRevisionName'] = revision
    current['status']['traffic'].append({
        'revisionName': revision,
        'tag': a.CHECK_TAG,
        'url': a.CHECK_URL,
    })
    immutable = {
        'metadata': {
            'name': revision,
            'namespace': c.NUMBER,
            'labels': {'serving.knative.dev/service': c.SERVICE},
            'annotations': deepcopy(current['spec']['template']['metadata']['annotations']),
        },
        'spec': deepcopy(current['spec']['template']['spec']),
        'status': {'conditions': [{'type':'Ready','status':'True'}]},
    }
    return before, policy, current, revision, image, immutable


class AccountStageTests(TestCase):
    def test_account_feature_must_be_absent_for_stage(self):
        svc, _, _ = fixture()
        self.assertTrue(a.account_feature_off(svc))
        svc = deepcopy(svc)
        svc['spec']['template']['spec']['containers'][0]['env'].append(
            {'name':'RICHON_ACCOUNT_ENABLED','value':'false'})
        with self.assertRaisesRegex(c.Stop,'account_feature_must_remain_off'):
            a.account_feature_off(svc)

    def test_known_old_startup_failure_is_allowed_only_for_recovery_precheck(self):
        svc, policy, revisions = fixture()
        def gc(*args, **kwargs):
            self.assertEqual(args[:3],('run','revisions','describe'))
            return revisions[args[3]]
        observations = {
            c.URL:'missing-key:500:non_json,wrong-key:500:non_json',
            e.CANDIDATE:'missing-key:500:non_json,wrong-key:500:non_json',
        }
        with patch.object(c,'gc',side_effect=gc),              patch.object(e,'access_status',return_value='signin-gateway-confirmed'),              patch.object(r,'safe_origin_observation',side_effect=lambda url:observations[url]),              patch.object(a.op,'summary'):
            a.validate_before(svc,policy)

    def test_unexpected_existing_origin_state_blocks_staging(self):
        svc, policy, revisions = fixture()
        def gc(*args, **kwargs):
            return revisions[args[3]]
        with patch.object(c,'gc',side_effect=gc),              patch.object(e,'access_status',return_value='signin-gateway-confirmed'),              patch.object(r,'safe_origin_observation',return_value='missing-key:200:non_json,wrong-key:200:non_json'),              patch.object(a.op,'summary'):
            with self.assertRaises(c.Stop):
                a.validate_before(svc,policy)

    def test_staged_revision_preserves_default_and_worker_candidate_routes(self):
        before, policy, current, revision, image, immutable = staged_fixture()
        with patch.object(c,'gc',return_value=immutable):
            a.verify_staged(before,policy,current,policy,revision,image)
        self.assertEqual(a.tagged_rows(current),a.expected_rows(revision))
        self.assertEqual(c.traffic(current),[(r.SERVING,100)])

    def test_staged_revision_rejects_traffic_or_worker_tag_change(self):
        before, policy, current, revision, image, immutable = staged_fixture()
        mutations = [
            lambda x:x['status']['traffic'][0].update(percent=99),
            lambda x:x['status']['traffic'][1].update(revisionName=revision),
            lambda x:x['status']['traffic'][1].update(tag='other'),
            lambda x:x['status']['traffic'][-1].update(percent=1),
        ]
        for mutate in mutations:
            changed=deepcopy(current); mutate(changed)
            with patch.object(c,'gc',return_value=immutable):
                with self.assertRaises(c.Stop):
                    a.verify_staged(before,policy,changed,policy,revision,image)

    def test_operation_is_explicitly_allowlisted_and_workflow_never_promotes_it(self):
        self.assertEqual(
            c.read_request({'operation':a.OPERATION,'request_id':'test'})['operation'],
            a.OPERATION)
        workflow=(c.ROOT/'.github/workflows/portal-deploy.yml').read_text()
        self.assertIn('"stage-account-code"',workflow)
        self.assertIn('python3 -B .github/portal/account_stage.py',workflow)
        # This operation must be handled by the edge-like branch and excluded
        # from the private promote path.
        self.assertNotIn('contains(fromJSON(\'["deploy","configure-internal-login","stage-account-code"]\')',workflow)
