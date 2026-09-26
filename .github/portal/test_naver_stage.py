"""Offline checks for owner-approved Naver v1 staging; no real credentials."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
import common as c
import edge_ops as e
from test_automation import service
from test_edge_ops import public_policy, receipt, candidate


def naver_receipt():
    state = receipt()
    state['request']['operation'] = 'stage-edge-naver'
    return state


def naver_candidate(state):
    result = candidate(state)
    intended = e.candidate_configuration(state['before'], 'stage-edge-naver')
    result['spec']['template']['spec']['containers'][0]['env'] = intended['spec']['template']['spec']['containers'][0]['env']
    return result


class NaverStageTests(TestCase):
    def test_new_mode_is_explicit_and_never_promotion(self):
        req = {'operation': 'stage-edge-naver', 'request_id': 'test'}
        self.assertEqual(c.read_request(req), req)
        with self.assertRaises(c.Stop):
            c.read_request({**req, 'operation': 'promote-edge-naver'})
        with self.assertRaises(c.Stop):
            c.read_request({**req, 'secrets': {'other': 'latest'}})

    def test_only_two_exact_refs_are_added_and_original_is_untouched(self):
        before = service(True); original = deepcopy(before)
        intended = e.candidate_configuration(before, 'stage-edge-naver')
        self.assertEqual(before, original)
        self.assertEqual(e.candidate_configuration(before, 'stage-edge'), before)
        actual = c.environment(intended['spec']['template']['spec']['containers'][0])
        old = c.environment(before['spec']['template']['spec']['containers'][0])
        self.assertEqual(set(actual) - set(old), set(c.NAVER_NAMES))
        self.assertEqual({k: actual[k] for k in old}, old)
        for name, secret in c.NAVER_NAMES.items():
            self.assertEqual(actual[name], {'name': name, 'valueFrom': {
                'secretKeyRef': {'name': secret, 'key': '1'}}})
        self.assertEqual(e.candidate_configuration(intended, 'stage-edge-naver'), intended)
        c.inspect(intended, public_policy(), boundary='edge')

    def test_existing_other_versions_or_partial_bindings_are_not_overwritten(self):
        for bad in ('2', 'latest'):
            value = e.candidate_configuration(service(True), 'stage-edge-naver')
            value['spec']['template']['spec']['containers'][0]['env'][-1]['valueFrom']['secretKeyRef']['key'] = bad
            with self.assertRaises(c.Stop):
                e.candidate_configuration(value, 'stage-edge-naver')
        value['spec']['template']['spec']['containers'][0]['env'].pop()
        with self.assertRaises(c.Stop):
            e.candidate_configuration(value, 'stage-edge-naver')

    def test_readback_requires_pinned_naver_and_preserves_other_env_and_traffic(self):
        state = naver_receipt()
        state.update(image=c.IMAGE+'@sha256:'+'b'*64, candidate=c.SERVICE+'-gh-123-1')
        value = naver_candidate(state)
        self.assertEqual(e.verify_candidate(state, value, public_policy()), e.CANDIDATE)
        mutations = (
            lambda s: s['spec']['template']['spec']['containers'][0]['env'].pop(),
            lambda s: s['status'].update(traffic=[{'revisionName': state['candidate'], 'percent': 100}]),
            lambda s: s['spec']['template']['spec'].update(serviceAccountName='other'),
            lambda s: s['metadata']['annotations'].update(extra='unexpected'),
        )
        for mutate in mutations:
            other = deepcopy(value); mutate(other)
            with self.assertRaises(c.Stop):
                e.verify_candidate(state, other, public_policy())

    def test_missing_access_confirmation_still_stops_before_any_cloud_writes(self):
        state = naver_receipt(); state['access'] = 'inconclusive'
        with patch.object(c, 'gc') as gc, patch.object(c, 'command') as command:
            with self.assertRaisesRegex(c.Stop, 'access_gateway_not_confirmed'):
                e.stage(state)
            gc.assert_not_called(); command.assert_not_called()

    def test_naver_stage_changes_one_image_plus_two_refs_without_traffic_or_iam(self):
        state = naver_receipt(); calls = []; count = 0
        def gc(*args, **kw):
            calls.append(args)
            if args[:4] == ('artifacts','docker','images','describe'):
                return {'image_summary': {'digest': 'sha256:'+'b'*64}}
            return {}
        def get():
            nonlocal count
            count += 1
            return (state['before'] if count <= 2 else naver_candidate(state)), public_policy()
        with patch.object(c,'source',return_value=state['sha']), patch.object(c,'gc',side_effect=gc), \
             patch.object(c,'command',return_value=''), patch.object(e,'get_service',side_effect=get), \
             patch.object(e,'access_status',return_value='signin-gateway-confirmed'), \
             patch.object(e,'probe_origin'), patch.object(e.op,'save'), patch.object(e.op,'summary'):
            e.stage(state)
        writes = [a for a in calls if a[:3] == ('run','services','update')]
        self.assertEqual(len(writes), 1)
        self.assertIn('--no-traffic', writes[0])
        self.assertIn('--update-secrets=NAVER_CLIENT_ID=richon-naver-client-id:1,NAVER_CLIENT_SECRET=richon-naver-client-secret:1', writes[0])
        self.assertFalse(any('update-traffic' in a or 'secrets' in a or 'set-iam-policy' in a for a in calls))
        self.assertFalse(any(x.startswith(('--set-secrets','--update-env-vars','--allow-unauthenticated')) for x in writes[0]))

    def test_access_report_checks_all_paths_without_sensitive_details(self):
        def response(url, **kwargs):
            if url.endswith('/auth/naver/callback'):
                return 403, {'CF-Ray': 'not-logged', 'Set-Cookie': 'never-log'}, b'private-body'
            if url in {e.ORIGIN + p for p in e.PUBLIC}:
                return 200, {'Content-Type': 'text/html'}, b''
            return 302, {'Location': 'https://' + e.ACCESS_HOST + '/cdn-cgi/access/login/richonacademy.com?token=secret-never-log'}, b''
        with patch.object(e, 'request', side_effect=response) as requests, patch.object(e.op, 'summary') as summary:
            self.assertEqual(e.access_status(), 'inconclusive')
        self.assertEqual(requests.call_count, len(e.PATHS + e.PUBLIC))
        output = '\n'.join(call.args[0] for call in summary.call_args_list)
        self.assertIn('/auth/naver/callback', output)
        self.assertIn('"status": 403', output)
        for secret in ('secret-never-log','not-logged','private-body','never-log'):
            self.assertNotIn(secret, output)

    def test_workflow_builds_before_auth_and_new_mode_never_enters_legacy_promote(self):
        text = (Path(__file__).resolve().parents[1] / 'workflows/portal-deploy.yml').read_text()
        self.assertIn('["deploy","stage-edge","stage-edge-naver","rollout-edge-code","stage-account-code","stage-marketing-enabled"]', text)
        self.assertIn('["inspect-edge","stage-edge","stage-edge-naver","rollout-edge-code","stage-account-code","stage-account-enabled","inspect-account-enabled","stage-marketing-enabled","inspect-marketing-enabled"]', text)
        self.assertIn('NAVER_CLIENT_ID=synthetic', text)
        self.assertLess(text.index('Build portal image'), text.index('- id: auth'))
        self.assertNotIn('secrets: inherit', text)
