"""Offline guards only: no real Google Cloud or Neon access."""
import copy
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import connect
import guard
import probe


def service():
    return {
        'metadata': {'name': guard.SERVICE, 'namespace': guard.PROJECT_NUMBER},
        'spec': {'template': {'metadata': {'annotations': {'autoscaling.knative.dev/maxScale': '1'}},
                              'spec': {'serviceAccountName': guard.RUNTIME,
                                       'containers': [{'image': guard.IMAGE_BASE + '@sha256:' + 'a' * 64,
                                                       'env': [{'name': 'DATABASE_URL', 'valueFrom': {
                                                           'secretKeyRef': {'name': 'richon-database-url', 'key': '2'}}}]}]}}},
        'status': {'url': guard.SERVICE_URL, 'latestReadyRevisionName': guard.SERVICE + '-ci-123-1',
                   'latestCreatedRevisionName': guard.SERVICE + '-ci-123-1',
                   'traffic': [{'revisionName': guard.SERVICE + '-ci-123-1', 'tag': 'ci-candidate',
                                'url': guard.SERVICE_URL.replace('https://', 'https://ci-candidate---')}]},
    }


class Guards(unittest.TestCase):
    def test_valid_service_and_candidate(self):
        self.assertEqual(guard.inspect_service(service(), {}), {'service_url': guard.SERVICE_URL})
        self.assertEqual(guard.inspect_service(service(), {}, guard.SERVICE + '-ci-123-1',
                                              guard.IMAGE_BASE + '@sha256:' + 'a' * 64)['revision'],
                         guard.SERVICE + '-ci-123-1')

    def test_wrong_project_and_service(self):
        for field in ('name', 'namespace'):
            obj = service()
            obj['metadata'][field] = 'other'
            with self.assertRaises(ValueError): guard.inspect_service(obj, {})

    def test_public_access_fails(self):
        for member in ('allUsers', 'allAuthenticatedUsers'):
            with self.assertRaises(ValueError):
                guard.inspect_service(service(), {'bindings': [{'members': [member]}]})
        obj = service()
        obj['metadata']['annotations'] = {'run.googleapis.com/invoker-iam-disabled': 'true'}
        with self.assertRaises(ValueError): guard.inspect_service(obj, {})

    def test_runtime_identity_fails(self):
        obj = service()
        obj['spec']['template']['spec']['serviceAccountName'] = 'other'
        with self.assertRaises(ValueError): guard.inspect_service(obj, {})

    def test_secret_payload_never_output(self):
        obj = service()
        obj['spec']['template']['spec']['containers'][0]['env'] = [{'name': 'DATABASE_URL', 'value': 'secret-marker'}]
        with self.assertRaises(ValueError) as exc: guard.inspect_service(obj, {})
        self.assertNotIn('secret-marker', str(exc.exception))

    def test_unpinned_secret_or_other_database_fails(self):
        for key, val in (('key', 'latest'), ('name', 'another-database')):
            obj = service()
            obj['spec']['template']['spec']['containers'][0]['env'][0]['valueFrom']['secretKeyRef'][key] = val
            with self.assertRaises(ValueError): guard.inspect_service(obj, {})

    def test_scaling_change_fails(self):
        obj = service()
        obj['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/maxScale'] = '100'
        with self.assertRaises(ValueError): guard.inspect_service(obj, {})

    def test_concurrent_revision_change_fails(self):
        obj = service()
        obj['status']['latestCreatedRevisionName'] = 'other'
        with self.assertRaises(ValueError):
            guard.inspect_service(obj, {}, guard.SERVICE + '-ci-123-1', guard.IMAGE_BASE + '@sha256:' + 'a' * 64)

    def test_external_candidate_url_fails(self):
        obj = service()
        obj['status']['traffic'][0]['url'] = 'https://attacker.invalid/'
        with self.assertRaises(ValueError):
            guard.inspect_service(obj, {}, guard.SERVICE + '-ci-123-1', guard.IMAGE_BASE + '@sha256:' + 'a' * 64)

    def test_wrong_image_fails(self):
        with self.assertRaises(ValueError):
            guard.inspect_service(service(), {}, guard.SERVICE + '-ci-123-1', guard.IMAGE_BASE + '@sha256:' + 'b' * 64)

    def test_provider_checks_all_trust_fields(self):
        config = {'attributeMapping': connect.MAPPING, 'attributeCondition': connect.CONDITION,
                  'oidc': {'issuerUri': 'https://token.actions.githubusercontent.com'}}
        self.assertTrue(connect.provider_is_expected(config))
        for field in ('repository_id', 'repository_owner_id', 'ref', 'workflow_ref', 'event_name'):
            self.assertIn('assertion.' + field, connect.CONDITION)
            self.assertIn('attribute.' + field, connect.MAPPING)
        for field in ('attributeMapping', 'attributeCondition', 'oidc'):
            bad = copy.deepcopy(config)
            bad[field] = {} if field != 'attributeCondition' else 'true'
            self.assertFalse(connect.provider_is_expected(bad))

    def test_cancel_does_not_mutate(self):
        def fake(*args, **kwargs):
            if args[:2] == ('projects', 'describe'): return {'projectNumber': guard.PROJECT_NUMBER}
            if args[:3] == ('run', 'services', 'describe'): return service()
            if args[:3] == ('run', 'services', 'get-iam-policy'): return {}
            self.fail('Unexpected mutation')
        with patch.object(connect, 'gcloud', side_effect=fake), patch('builtins.input', return_value='NO'), \
             patch.object(connect.shutil, 'which', return_value='/gcloud'):
            self.assertEqual(connect.main(), 0)

    def test_iam_retry_is_bounded(self):
        good = SimpleNamespace(returncode=0, stdout='{}', stderr='')
        bad = SimpleNamespace(returncode=1, stdout='', stderr='not yet visible')
        with patch.object(connect.subprocess, 'run', side_effect=[bad, good]) as run, \
             patch.object(connect.time, 'sleep') as sleep:
            connect.gcloud('iam', 'service-accounts', 'describe', 'test', attempts=3)
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(5)

    def test_probe_refuses_external_url(self):
        with patch.dict(probe.os.environ, {'CANDIDATE_URL': 'https://attacker.invalid', 'TEST_ID_TOKEN': 'dummy'}), \
             patch.object(probe.urllib.request, 'build_opener') as opener:
            with self.assertRaises(ValueError): probe.main()
            opener.assert_not_called()

    def test_redirects_are_not_followed(self):
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, None, None, 'https://other.invalid'))


if __name__ == '__main__':
    unittest.main()
