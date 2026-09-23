"""Only the revision-template gcloud nonce is non-semantic for comparison."""
from copy import deepcopy
import unittest
import common as c
import operate as op
from test_automation import service, candidate_state

NONCE = 'client.knative.dev/nonce'


class NonceComparisonTests(unittest.TestCase):
    def test_nonce_changes_do_not_block_otherwise_valid_candidate(self):
        state, svc = candidate_state('configure-internal-login')
        state['before']['spec']['template']['metadata']['labels'] = {NONCE: 'old'}
        svc['spec']['template']['metadata']['labels'] = {NONCE: 'new'}
        op.verify_candidate(state, svc, {})

    def test_absent_empty_or_nonce_only_labels_equivalent(self):
        original = service()
        for labels in ({}, {NONCE: 'generated'}):
            changed = deepcopy(original)
            changed['spec']['template']['metadata']['labels'] = labels
            self.assertEqual(c.protected(original), c.protected(changed))

    def test_custom_template_labels_are_still_protected(self):
        state, svc = candidate_state()
        svc['spec']['template']['metadata']['labels'] = {NONCE: 'new', 'owner-policy': 'changed'}
        with self.assertRaisesRegex(c.Stop, 'unexpected_configuration_change'):
            op.verify_candidate(state, svc, {})

    def test_container_name_is_not_ignored(self):
        state, svc = candidate_state()
        svc['spec']['template']['spec']['containers'][0]['name'] = 'renamed'
        with self.assertRaisesRegex(c.Stop, 'unexpected_configuration_change'):
            op.verify_candidate(state, svc, {})

    def test_service_level_nonce_and_labels_not_ignored(self):
        state, svc = candidate_state()
        svc['metadata']['labels'][NONCE] = 'unreviewed-service-label'
        with self.assertRaisesRegex(c.Stop, 'unexpected_configuration_change'):
            op.verify_candidate(state, svc, {})

    def test_original_input_is_not_modified(self):
        original = service()
        original['spec']['template']['metadata']['labels'] = {NONCE: 'unchanged', 'custom': 'preserve'}
        saved = deepcopy(original)
        c.protected(original)
        self.assertEqual(original, saved)


if __name__ == '__main__':
    unittest.main()
