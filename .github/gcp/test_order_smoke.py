"""Offline verification of the bounded live-smoke client. Never makes HTTP calls."""
import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import order_smoke as smoke
from test_connection import service


class OrderSmokeTests(unittest.TestCase):
    def test_modes_are_explicit_and_reject_unapproved_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'request'
            for payload, expected in [({'operation': 'deploy'}, 'deploy'),
                                      ({'operation': 'order-smoke', 'course_id': smoke.COURSE,
                                        'allow_synthetic_orders': True}, 'order-smoke')]:
                path.write_text(json.dumps(payload))
                self.assertEqual(smoke.mode(path), expected)
            for payload in [{}, [], {'operation': 'unknown'}, {'operation': 'order-smoke'},
                            {'operation': 'order-smoke', 'course_id': 'real-course',
                             'allow_synthetic_orders': True},
                            {'operation': 'deploy', 'arbitrary_command': 'forbidden'}]:
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    smoke.mode(path)

    def test_pinned_service_checks_exact_image_revision_and_traffic(self):
        obj = service()
        obj['spec']['template']['spec']['containers'][0]['image'] = smoke.IMAGE
        obj['status'].update(latestReadyRevisionName=smoke.REVISION,
                             latestCreatedRevisionName=smoke.REVISION,
                             traffic=[{'revisionName': smoke.REVISION, 'percent': 100}])
        smoke.pinned_service(obj, {})
        obj['status']['traffic'][0]['revisionName'] = 'unexpected'
        with self.assertRaises(ValueError):
            smoke.pinned_service(obj, {})

    def test_only_test_paths_and_fixed_course_may_be_sent(self):
        with patch.object(smoke.urllib.request, 'build_opener') as opener:
            for path, body in [('/admin', None), ('https://outside.invalid/', None),
                               ('/orders', {'course_id': 'actual-customer-course'})]:
                with self.assertRaises(ValueError):
                    smoke.request(path, 'dummy', body)
            opener.assert_not_called()

    def test_redirects_never_forward_credentials(self):
        self.assertIsNone(smoke.NoRedirect().redirect_request(None, None, 302, None, None,
                                                              'https://outside.invalid'))

    def test_missing_token_stops_before_network(self):
        with patch.object(smoke, 'request') as request:
            with self.assertRaises(ValueError):
                smoke.verify('', send=request)
            request.assert_not_called()

    def test_errors_do_not_expose_unexpected_body(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(ValueError):
                smoke.checked_order((503, {'detail': 'secret-marker'}))
        self.assertNotIn('secret-marker', output.getvalue())

    def test_full_sequence_and_repeated_run_are_bounded_to_two_keys(self):
        stored = {}
        lock = threading.Lock()
        def send(path, token, body=None, key=None):
            if not token:
                return 403, None
            if path == '/health':
                return 200, {'status': 'ok'}
            if set(body) != set(smoke.BODY):
                return 422, {'detail': 'invalid_request'}
            if body != smoke.BODY:
                return 409, {'detail': 'idempotency_conflict'}
            with lock:
                if key in stored:
                    return 200, stored[key]
                stored[key] = {
                    'order_id': 'ord_' + ('a' if key == smoke.KEY else 'b') * 32,
                    'course_id': smoke.COURSE, 'course_title': smoke.TITLE,
                    'cohort': smoke.COHORT, 'amount_krw': 1000, 'currency': 'KRW',
                    'status': 'pending_payment', 'created_at': '2026-09-22T00:00:00Z'}
                return 201, stored[key]
        first = smoke.verify('dummy', send)
        second = smoke.verify('dummy', send)
        self.assertEqual(first['sequential_statuses'], [201, 200])
        self.assertEqual(first['concurrent_statuses'], [200, 200, 200, 201])
        self.assertEqual(second['sequential_statuses'], [200, 200])
        self.assertEqual(second['concurrent_statuses'], [200] * 4)
        self.assertEqual(len(stored), 2)
        self.assertEqual(first['order_ids'], second['order_ids'])
        for secret in ['dummy', smoke.BODY['customer_phone'], smoke.BODY['customer_email']]:
            self.assertNotIn(secret, json.dumps(first))


if __name__ == '__main__':
    unittest.main()
