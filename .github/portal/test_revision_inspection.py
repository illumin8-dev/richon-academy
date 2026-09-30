"""Offline metadata/probe tests, never real GCP."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch, call
import common as c
import revision_inspection as ri
from test_automation import service


def fixture():
    before = service()
    before['spec']['template']['metadata']['labels'] = {ri.NONCE: 'old-private-value'}
    after = c.intended(before, 'configure-internal-login')
    after['spec']['template']['metadata']['labels'][ri.NONCE] = 'new-private-value'
    name = c.SERVICE + '-gh-123-1'
    after['status']['latestCreatedRevisionName'] = name
    after['status']['latestReadyRevisionName'] = name
    after['status']['traffic'].append({'tag': c.TAG, 'revisionName': name,
        'url': 'https://' + c.TAG + '---' + c.URL.split('://')[1]})
    revision = {'metadata': deepcopy(before['spec']['template']['metadata']),
                'spec': deepcopy(before['spec']['template']['spec']),
                'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}
    revision['metadata'].update(name=c.traffic(before)[0][0], namespace=c.NUMBER)
    revision['metadata']['labels']['serving.knative.dev/service'] = c.SERVICE
    state = {'request': {'operation': 'inspect'}, 'before': after, 'policy': {}}
    return state, revision


class RevisionInspectionTests(unittest.TestCase):
    def test_pending_candidate_does_not_replace_serving_probe_mode(self):
        state, revision = fixture(); probe = Mock(); output = []
        with patch.object(c, 'gc', return_value=revision) as gc, patch.object(c, 'get_service', return_value=(state['before'], {})):
            ri.inspect_pending(state, probe, output.append)
        gc.assert_called_once_with('run', 'revisions', 'describe', revision['metadata']['name'], '--region=' + c.REGION)
        self.assertEqual(probe.call_args_list, [call(c.URL, False, authenticated=False), call(c.URL, False),
            call('https://' + c.TAG + '---' + c.URL.split('://')[1], True, authenticated=False),
            call('https://' + c.TAG + '---' + c.URL.split('://')[1], True)])
        self.assertIn('DIAGNOSTIC template spec after approved env: same', output)
        self.assertIn('DIAGNOSTIC template label client.knative.dev/nonce: different', output)
        self.assertNotIn('private-value', '\n'.join(output))
        self.assertTrue(output[-1].startswith('PORTAL INSPECT PASSED'))

    def test_no_pending_candidate_needs_no_revision_query(self):
        svc = service(); state = {'request': {'operation': 'inspect'}, 'before': svc, 'policy': {}}
        with patch.object(c, 'gc') as gc, patch.object(c, 'get_service', return_value=(svc, {})):
            probe = Mock(); ri.inspect_pending(state, probe, Mock())
            self.assertEqual(probe.call_count, 2); gc.assert_not_called()

    def test_foreign_revision_identity_rejected(self):
        for key in ('name', 'namespace'):
            state, revision = fixture(); revision['metadata'][key] = 'foreign'
            with self.subTest(key=key), self.assertRaises(c.Stop):
                ri.serving_view(state['before'], {}, revision)
        state, revision = fixture(); revision['metadata']['labels']['serving.knative.dev/service'] = 'other'
        with self.assertRaises(c.Stop): ri.serving_view(state['before'], {}, revision)

    def test_serving_runtime_and_secret_guards_still_apply(self):
        state, revision = fixture(); revision['spec']['serviceAccountName'] = 'other'
        with self.assertRaises(c.Stop): ri.serving_view(state['before'], {}, revision)
        state, revision = fixture(); revision['spec']['containers'][0]['env'][-1] = {'name': 'RICHON_EDGE_SECRET', 'value': 'PRIVATE'}
        with self.assertRaises(c.Stop): ri.serving_view(state['before'], {}, revision)

    def test_revision_not_ready_rejected(self):
        state, revision = fixture(); revision['status']['conditions'][0]['status'] = 'False'
        with self.assertRaises(c.Stop): ri.serving_view(state['before'], {}, revision)

    def test_diagnostics_never_echo_unknown_keys_or_values(self):
        state, revision = fixture(); svc = state['before']
        view = ri.serving_view(svc, {}, revision)
        svc['spec']['template']['metadata']['labels']['PRIVATE-KEY'] = 'PRIVATE-VALUE'
        svc['spec']['template']['metadata']['annotations']['PRIVATE-ANNOTATION'] = 'PRIVATE-VALUE'
        svc['spec']['template']['spec']['PRIVATE-FIELD'] = 'PRIVATE-VALUE'
        output = '\n'.join(ri.differences(svc, view))
        self.assertNotIn('PRIVATE', output)
        self.assertIn('other spec field differences: 1', output)
        self.assertIn('other declared template label differences: 1', output)
        self.assertIn('other declared template annotation differences: 1', output)

    def test_concurrent_traffic_change_is_rejected(self):
        state, revision = fixture(); changed = deepcopy(state['before'])
        changed['status']['traffic'] = [{'revisionName': changed['status']['latestReadyRevisionName'], 'percent': 100}]
        with patch.object(c, 'gc', return_value=revision), patch.object(c, 'get_service', return_value=(changed, {})):
            with self.assertRaisesRegex(c.Stop, 'service_changed_during_inspection'):
                ri.inspect_pending(state, Mock(), Mock())

    def test_only_inspect_operation_permitted(self):
        state, _ = fixture(); state['request']['operation'] = 'deploy'
        with patch.object(c, 'gc') as gc, self.assertRaises(c.Stop):
            ri.inspect_pending(state, Mock(), Mock())
        gc.assert_not_called()


if __name__ == '__main__':
    unittest.main()
