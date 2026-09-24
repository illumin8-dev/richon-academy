"""Offline regression for honest deployment-probe identification; no network."""
from unittest import TestCase
from unittest.mock import Mock, patch
import common as c
import edge_ops as e


class Response:
    code = 403
    headers = {'Content-Type': 'text/html'}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit):
        assert limit == 8193
        return b'denied'


class ProbeIdentity(TestCase):
    def test_all_allowed_gets_use_stable_truthful_agent_without_credentials(self):
        self.assertEqual(e.PROBE_USER_AGENT, 'RichonPortalDeployCheck/1.0')
        opener = Mock(); opener.open.return_value = Response()
        with patch.object(e.urllib.request, 'build_opener', return_value=opener) as build:
            for url in sorted(e.URLS):
                with self.subTest(url=url):
                    e.request(url)
                    req = opener.open.call_args.args[0]
                    self.assertEqual(req.full_url, url)
                    self.assertEqual(req.get_method(), 'GET')
                    self.assertIsNone(req.data)
                    self.assertEqual({k.lower(): v for k, v in req.header_items()}, {
                        'accept': 'text/html', 'user-agent': e.PROBE_USER_AGENT})
                    self.assertEqual(opener.open.call_args.kwargs, {'timeout': 25})
                    self.assertIsInstance(build.call_args.args[1], e.op.NoRedirect)

    def test_wrong_key_test_remains_origin_only_and_explicitly_invalid(self):
        opener = Mock(); opener.open.return_value = Response()
        with patch.object(e.urllib.request, 'build_opener', return_value=opener):
            e.request(c.URL + '/auth/login', wrong_key=True)
            req = opener.open.call_args.args[0]
            headers = {k.lower(): v for k, v in req.header_items()}
            self.assertEqual(headers['x-richon-edge-key'], 'deliberately-invalid-test-key')
            self.assertEqual(headers['user-agent'], e.PROBE_USER_AGENT)
            self.assertEqual(set(headers), {'accept', 'user-agent', 'x-richon-edge-key'})
            opener.open.reset_mock()
            with self.assertRaises(c.Stop):
                e.request(e.ORIGIN + '/auth/login', wrong_key=True)
            opener.open.assert_not_called()

    def test_public_requests_are_still_six_exact_queryless_paths(self):
        expected = {'/', '/apply.html', '/auth/login', '/auth/kakao/callback',
                    '/auth/naver/callback', '/portal/mypage'}
        self.assertEqual(set(e.PATHS + e.PUBLIC), expected)
        with patch.object(e.urllib.request, 'build_opener') as build:
            for suffix in ('/auth/start', '/auth/me', '/auth/login?code=x',
                           '/auth/kakao/callback?state=x', '/portal/admin'):
                with self.subTest(suffix=suffix), self.assertRaises(c.Stop):
                    e.request(e.ORIGIN + suffix)
            with self.assertRaises(c.Stop): e.request('https://example.invalid/')
            build.assert_not_called()

    def test_user_agent_is_not_a_pass_for_block_challenge_or_open_login(self):
        for response in (
            (403, {'CF-Ray': 'not-authentication'}, b''),
            (403, {'CF-Mitigated': 'challenge'}, b''),
            (200, {'Content-Type': 'text/html'}, b'login open without Access'),
        ):
            with self.subTest(status=response[0]), patch.object(e, 'request', return_value=response), \
                 patch.object(e.op, 'summary'):
                self.assertEqual(e.access_status(), 'inconclusive')

    def test_identification_does_not_change_authenticated_gate_requirements(self):
        from test_edge_ops import receipt
        state = receipt(); state['request']['operation'] = 'stage-edge-naver'
        state['access'] = 'inconclusive'
        with patch.object(c, 'gc') as gc, patch.object(c, 'command') as command:
            with self.assertRaisesRegex(c.Stop, 'access_gateway_not_confirmed'):
                e.stage(state)
            gc.assert_not_called(); command.assert_not_called()
