"""Offline edge-gate operation tests; no cloud, network, or real credentials."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
import common as c
import edge_ops as e
from test_automation import service


def public_policy():
    return {'bindings': [{'role': 'roles/run.invoker', 'members': ['allUsers', 'serviceAccount:deployer@example.invalid']} ]}


def receipt():
    return {'sha': 'b'*40, 'run': '123', 'attempt': '1',
            'request': {'operation': 'stage-edge', 'request_id': 'offline'},
            'before': service(True), 'policy': public_policy(), 'access': 'signin-gateway-confirmed'}


def candidate(state):
    svc = deepcopy(state['before'])
    svc['spec']['template']['spec']['containers'][0]['image'] = state['image']
    svc['status']['latestCreatedRevisionName'] = state['candidate']
    svc['status']['latestReadyRevisionName'] = state['candidate']
    svc['status']['traffic'].append({'tag': c.TAG, 'revisionName': state['candidate'], 'url': e.CANDIDATE})
    return svc


class EdgeGuards(TestCase):
    def test_explicit_modes_only(self):
        for name in ('inspect-edge', 'stage-edge'):
            self.assertEqual(c.read_request({'operation': name, 'request_id': 'test'})['operation'], name)
        for name in ('promote-edge', 'migrate', 'enable-naver'):
            with self.assertRaises(c.Stop): c.read_request({'operation': name, 'request_id': 'test'})

    def test_legacy_private_default_still_rejects_public(self):
        with self.assertRaises(c.Stop): c.inspect(service(True), public_policy())
        self.assertTrue(c.inspect(service(True), public_policy(), boundary='edge')['enabled'])

    def test_missing_and_unknown_boundary_are_rejected(self):
        with self.assertRaises(c.Stop): c.inspect(service(True), {}, boundary='edge')
        with self.assertRaises(c.Stop): c.inspect(service(True), {}, boundary='skip')

    def test_public_principals_and_grants_are_exact(self):
        variants = [
            {'role': 'roles/run.admin', 'members': ['allUsers']},
            {'role': 'roles/run.invoker', 'members': ['allAuthenticatedUsers']},
            {'role': 'roles/run.invoker', 'members': ['allUsers'], 'condition': {'expression': 'true'}},
            {'role': 'roles/run.invoker', 'members': ['allUsers', 'allUsers']},
        ]
        for bad in variants:
            with self.subTest(bad=bad), self.assertRaises(c.Stop):
                c.inspect(service(True), {'bindings': [bad]}, boundary='edge')
        p = public_policy(); p['bindings'].append(deepcopy(p['bindings'][0]))
        with self.assertRaises(c.Stop): c.inspect(service(True), p, boundary='edge')

    def test_disabled_iam_check_or_different_ingress_rejected(self):
        for key, value in (('run.googleapis.com/invoker-iam-disabled', 'true'),
                           ('run.googleapis.com/ingress', 'internal')):
            svc = service(True); svc['metadata']['annotations'][key] = value
            with self.assertRaises(c.Stop): c.inspect(svc, public_policy(), boundary='edge')

    def test_disabled_app_gate_rejected(self):
        with self.assertRaises(c.Stop): c.inspect(service(False), public_policy(), boundary='edge')

    def test_all_resource_and_env_guards_still_apply(self):
        for mutate in (
            lambda s: s['spec']['template']['spec'].update(serviceAccountName='other@example.invalid'),
            lambda s: s['spec']['template']['spec'].update(containerConcurrency=80),
            lambda s: s['spec']['template']['spec']['containers'][0].update(image=c.IMAGE+':latest'),
            lambda s: s['spec']['template']['spec']['containers'][0]['env'].append({'name':'NAVER_CLIENT_ID','value':'not-approved'}),
            lambda s: s['spec']['template']['spec']['containers'][0]['env'].append({'name':'RICHON_EDGE_SECRET','value':'plaintext'}),
        ):
            svc = service(True); mutate(svc)
            with self.assertRaises(c.Stop): c.inspect(svc, public_policy(), boundary='edge')

    def test_plain_and_wrong_keys_both_probe_exact_application_rejection(self):
        response = (403, {'Content-Type':'application/json'}, b'{"detail":"edge_required"}')
        with patch.object(e, 'request', return_value=response) as req:
            e.probe_origin(c.URL)
        self.assertEqual([x.kwargs['wrong_key'] for x in req.call_args_list], [False, True])

    def test_generic_403_or_503_or_html_or_other_json_is_not_a_pass(self):
        for response in ((403, {'Content-Type':'text/html'}, b'denied'),
                         (503, {'Content-Type':'application/json'}, b'{"detail":"portal_not_enabled"}'),
                         (403, {'Content-Type':'application/json'}, b'{}'),
                         (403, {'Content-Type':'application/json'}, b'invalid'),
                         (200, {'Content-Type':'application/json'}, b'{"detail":"edge_required"}')):
            with patch.object(e, 'request', return_value=response), self.assertRaises(c.Stop):
                e.probe_origin(c.URL)

    def test_probe_target_and_headers_are_allowlisted(self):
        for url in ('https://evil.invalid', c.URL + '/auth/start', e.ORIGIN + '/auth/start'):
            with self.assertRaises(c.Stop): e.request(url)
        with self.assertRaises(c.Stop): e.request(e.ORIGIN + '/', wrong_key=True)

    def test_redirect_is_not_followed(self):
        self.assertIsNone(e.op.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid'))

    def test_access_403_is_inconclusive(self):
        with patch.object(e, 'request', return_value=(403, {}, b'')):
            self.assertEqual(e.access_status(), 'inconclusive')

    def test_access_confirmation_requires_correct_tenant_and_public_pages(self):
        def response(url, **kw):
            if url in {e.ORIGIN + p for p in e.PUBLIC}:
                return 200, {'Content-Type': 'text/html'}, b''
            return 302, {'Location': 'https://' + e.ACCESS_HOST + '/cdn-cgi/access/login/richonacademy.com?kid=x'}, b''
        with patch.object(e, 'request', side_effect=response):
            self.assertEqual(e.access_status(), 'signin-gateway-confirmed')
        with patch.object(e, 'request', return_value=(302, {'Location':'https://evil.invalid/cdn-cgi/access/login/richonacademy.com'}, b'')):
            self.assertEqual(e.access_status(), 'inconclusive')

    def test_changed_policy_config_or_traffic_rejected(self):
        before = service(True)
        for mutate in (
            lambda s: s['spec'].update(traffic=[]),
            lambda s: s['status'].update(traffic=[]),
            lambda s: s['metadata']['annotations'].update(extra='unexpected'),
        ):
            current = deepcopy(before); mutate(current)
            with self.assertRaises(c.Stop): e.unchanged(before, public_policy(), current, public_policy())
        with self.assertRaises(c.Stop): e.unchanged(before, public_policy(), before, {})

    def test_candidate_keeps_policy_config_and_serving_traffic(self):
        state = receipt(); state.update(image=c.IMAGE+'@sha256:'+'b'*64, candidate=c.SERVICE+'-gh-123-1')
        svc = candidate(state)
        self.assertEqual(e.verify_candidate(state, svc, public_policy()), e.CANDIDATE)
        svc['status']['traffic'] = [{'revisionName':state['candidate'], 'percent':100}]
        with self.assertRaises(c.Stop): e.verify_candidate(state, svc, public_policy())

    def test_stage_stops_without_access_confirmation_before_any_writes(self):
        state = receipt(); state['access'] = 'inconclusive'
        with patch.object(c, 'gc') as gc, patch.object(c, 'command') as command:
            with self.assertRaises(c.Stop): e.stage(state)
            gc.assert_not_called(); command.assert_not_called()

    def test_staging_writes_only_image_without_traffic_or_iam_update(self):
        state = receipt(); calls = []
        def gc(*args, **kw):
            calls.append(args)
            if args[:4] == ('artifacts','docker','images','describe'):
                return {'image_summary': {'digest':'sha256:'+'b'*64}}
            return {}
        get_count = 0
        def get():
            nonlocal get_count
            get_count += 1
            return (state['before'] if get_count <= 2 else candidate(state)), public_policy()
        with patch.object(c,'source',return_value=state['sha']), patch.object(c,'gc',side_effect=gc), \
             patch.object(c,'command',return_value=''), patch.object(e,'get_service',side_effect=get), \
             patch.object(e,'access_status',return_value='signin-gateway-confirmed'), \
             patch.object(e,'probe_origin'), patch.object(e.op,'save'), patch.object(e.op,'summary'):
            e.stage(state)
        writes = [args for args in calls if args[:3] == ('run','services','update')]
        self.assertEqual(len(writes),1)
        self.assertIn('--no-traffic',writes[0])
        self.assertFalse(any('update-traffic' in args or any('iam-policy' in arg for arg in args) for args in calls))
        self.assertFalse(any(arg.startswith(('--update-env-vars','--set-secrets','--update-secrets')) for arg in writes[0]))

    def test_inspect_is_read_only_even_when_access_is_inconclusive(self):
        svc = service(True)
        with patch.dict('os.environ',{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}), \
             patch.object(c,'source',return_value='b'*40), \
             patch.object(c,'read_request',return_value={'operation':'inspect-edge','request_id':'test'}), \
             patch.object(e,'get_service',return_value=(svc,public_policy())), \
             patch.object(e,'probe_origin'), patch.object(e,'access_status',return_value='inconclusive'), \
             patch.object(e.op,'save'), patch.object(e.op,'summary') as summary, patch.object(e,'stage') as stage:
            e.main()
        stage.assert_not_called()
        output = ' '.join(x.args[0] for x in summary.call_args_list)
        self.assertIn('inconclusive',output)
        self.assertIn('Database migration 008: NOT CHECKED',output)
        self.assertNotIn('IAM private',output)

    def test_workflow_keeps_cloud_identity_on_fixed_push_request(self):
        text = (Path(__file__).resolve().parents[1]/'workflows/portal-deploy.yml').read_text()
        self.assertIn("paths: ['.github/portal-deploy.request']", text)
        self.assertIn('python3 -B .github/portal/edge_ops.py', text)
        self.assertIn("['feat/backend-portal-deploy']", text)
        self.assertNotIn('pull_request_target', text)
        self.assertNotIn('secrets: inherit', text)
        source = Path(e.__file__).read_text()
        for forbidden in ('update-traffic', 'set-iam-policy', 'add-iam-policy-binding', 'versions access', 'import psycopg'):
            self.assertNotIn(forbidden, source)
