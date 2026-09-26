"""Offline only. Fake services, subprocesses and HTTP responses; never real GCP."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock
import common as c
import connect
import operate as op


def service(enabled=False):
    env = {**c.PLAIN, **{k: 'false' for k in c.FLAGS}}
    if enabled:
        env.update(c.INTERNAL)
    return {
        'metadata': {'name': c.SERVICE, 'namespace': c.NUMBER,
                     'labels': {'managed-by': 'richon-portal-bootstrap-v1'},
                     'annotations': {'run.googleapis.com/minScale': '0', 'run.googleapis.com/maxScale': '1'}},
        'spec': {'template': {'metadata': {'annotations': {'autoscaling.knative.dev/maxScale': '1'}},
                  'spec': {'serviceAccountName': c.RUNTIME, 'containerConcurrency': 20, 'timeoutSeconds': 60,
                           'containers': [{'image': c.IMAGE + '@sha256:' + 'a' * 64,
                           'resources': {'limits': {'cpu': '1', 'memory': '512Mi'}},
                           'env': [{'name': k, 'value': v} for k, v in env.items()] + [
                               {'name': k, 'valueFrom': {'secretKeyRef': {'name': v, 'key': '1'}}}
                               for k, v in c.SECRET_NAMES.items()]}]}},
                 'traffic': [{'latestRevision': True, 'percent': 100}]},
        'status': {'url': c.URL, 'latestCreatedRevisionName': c.SERVICE + '-00003-abc',
                   'latestReadyRevisionName': c.SERVICE + '-00003-abc',
                   'conditions': [{'type': 'Ready', 'status': 'True'}],
                   'traffic': [{'revisionName': c.SERVICE + '-00003-abc', 'percent': 100}]}}


def candidate_state(operation='deploy'):
    before = service()
    state = {'before': before, 'policy': {}, 'request': {'operation': operation, 'request_id': 'test'},
             'candidate': c.SERVICE + '-gh-123-1', 'image': c.IMAGE + '@sha256:' + 'b' * 64}
    after = c.intended(before, operation)
    after['spec']['template']['spec']['containers'][0]['image'] = state['image']
    after['status']['latestCreatedRevisionName'] = state['candidate']
    after['status']['latestReadyRevisionName'] = state['candidate']
    after['status']['traffic'].append({'tag': c.TAG, 'revisionName': state['candidate'],
                                     'url': 'https://' + c.TAG + '---' + c.URL.split('://')[1]})
    return state, after


class GuardTests(unittest.TestCase):
    def test_prepared_private_service_passes(self):
        self.assertFalse(c.inspect(service(), {})['enabled'])
        self.assertTrue(c.inspect(service(True), {})['enabled'])

    def test_wrong_service_or_project(self):
        for key, value in [('name', 'richon-backend-test'), ('namespace', '999')]:
            svc = service(); svc['metadata'][key] = value
            with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_public_iam_or_disabled_invoker_rejected(self):
        for member in ('allUsers', 'allAuthenticatedUsers'):
            with self.assertRaises(c.Stop):
                c.inspect(service(), {'bindings': [{'role': 'roles/run.invoker', 'members': [member]}]})
        svc = service(); svc['metadata']['annotations']['run.googleapis.com/invoker-iam-disabled'] = 'true'
        with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_foreign_runtime_and_resources_rejected(self):
        for key, value in [('serviceAccountName', 'other@example.invalid'), ('containerConcurrency', 80), ('timeoutSeconds', 300)]:
            svc = service(); svc['spec']['template']['spec'][key] = value
            with self.assertRaises(c.Stop): c.inspect(svc, {})
        svc = service(); svc['spec']['template']['spec']['containers'][0]['resources']['limits']['cpu'] = '4'
        with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_no_plaintext_or_latest_secret(self):
        for key in c.SECRET_NAMES:
            for replacement in ({'name': key, 'value': 'PRIVATE'}, {'name': key, 'valueFrom': {'secretKeyRef': {'name': c.SECRET_NAMES[key], 'key': 'latest'}}}):
                svc = service(); env = svc['spec']['template']['spec']['containers'][0]['env']
                env[:] = [replacement if row['name'] == key else row for row in env]
                with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_entry_override_and_extra_mount_blocked(self):
        for key, value in [('command', ['sh']), ('args', ['-c', 'echo bad']), ('volumeMounts', [{'name': 'secret'}])]:
            svc = service(); svc['spec']['template']['spec']['containers'][0][key] = value
            with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_flags_must_not_partially_enable(self):
        svc = service(); env = svc['spec']['template']['spec']['containers'][0]['env']
        next(x for x in env if x['name'] == c.FLAGS[0])['value'] = 'true'
        with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_future_module_or_policy_requires_review(self):
        for key, value in [('RICHON_MANUAL_ENABLED', 'true'), ('RICHON_TERMS_VERSION', 'production-v1')]:
            svc = service(True); env = svc['spec']['template']['spec']['containers'][0]['env']
            next(x for x in env if x['name'] == key)['value'] = value
            with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_unknown_or_duplicate_env_rejected(self):
        for item in ({'name': 'NAVER_CLIENT_SECRET', 'value': 'PRIVATE'}, {'name': 'KAKAO_APP_ID', 'value': '1585992'}):
            svc = service(); svc['spec']['template']['spec']['containers'][0]['env'].append(item)
            with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_unpinned_or_wrong_repository_image(self):
        for image in (c.IMAGE + ':latest', c.IMAGE.replace('richon-portal-ci', 'richon-backend-ci') + '@sha256:' + 'a' * 64):
            svc = service(); svc['spec']['template']['spec']['containers'][0]['image'] = image
            with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_scaling_is_bounded(self):
        for key, value in [('run.googleapis.com/minScale', '1'), ('run.googleapis.com/maxScale', '3')]:
            svc = service(); svc['metadata']['annotations'][key] = value
            with self.assertRaises(c.Stop): c.inspect(svc, {})

    def test_not_ready_blocks_changes_but_metadata_diagnosis_allowed(self):
        svc = service(); svc['status']['conditions'][0]['status'] = 'False'
        with self.assertRaises(c.Stop): c.inspect(svc, {})
        c.inspect(svc, {}, require_ready=False)

    def test_request_allowlist_and_no_arbitrary_args(self):
        for operation in ('hold', 'inspect', 'deploy', 'configure-internal-login', 'stage-account-code', 'stage-account-enabled', 'inspect-account-enabled', 'stage-marketing-enabled', 'inspect-marketing-enabled'):
            self.assertEqual(c.read_request({'operation': operation, 'request_id': 'test'})['operation'], operation)
        for value in ({'operation': 'publish', 'request_id': 'x'}, {'operation': 'deploy', 'request_id': 'x', 'args': '--allow-unauthenticated'}, {'operation': 'deploy', 'request_id': 'x\nSECRET'}):
            with self.assertRaises(c.Stop): c.read_request(value)

    def test_account_enabled_config_requires_exact_member_info_pair(self):
        svc = service(True)
        env = c.environment(svc['spec']['template']['spec']['containers'][0])
        env.update({
            'RICHON_ACCOUNT_ENABLED': {'name':'RICHON_ACCOUNT_ENABLED','value':'true'},
            'RICHON_TERMS_VERSION': {'name':'RICHON_TERMS_VERSION','value':'member-info-v1'},
            'RICHON_PRIVACY_VERSION': {'name':'RICHON_PRIVACY_VERSION','value':'member-info-v1'},
        })
        svc['spec']['template']['spec']['containers'][0]['env'] = list(env.values())
        self.assertTrue(c.inspect(svc, {})['account_enabled'])
        for key,value in (
            ('RICHON_ACCOUNT_ENABLED','false'),
            ('RICHON_TERMS_VERSION','internal-test-v1'),
            ('RICHON_PRIVACY_VERSION','internal-test-v1'),
        ):
            bad=deepcopy(svc)
            bad_env=c.environment(bad['spec']['template']['spec']['containers'][0])
            bad_env[key]['value']=value
            bad['spec']['template']['spec']['containers'][0]['env']=list(bad_env.values())
            with self.subTest(key=key), self.assertRaises(c.Stop):
                c.inspect(bad, {})

    def test_marketing_flag_requires_exact_account_enabled_policy(self):
        svc = service(True)
        env = c.environment(svc['spec']['template']['spec']['containers'][0])
        env.update({
            'RICHON_ACCOUNT_ENABLED': {'name':'RICHON_ACCOUNT_ENABLED','value':'true'},
            'RICHON_MARKETING_CONSENT_ENABLED': {'name':'RICHON_MARKETING_CONSENT_ENABLED','value':'true'},
            'RICHON_TERMS_VERSION': {'name':'RICHON_TERMS_VERSION','value':'member-info-v1'},
            'RICHON_PRIVACY_VERSION': {'name':'RICHON_PRIVACY_VERSION','value':'member-info-v1'},
        })
        svc['spec']['template']['spec']['containers'][0]['env']=list(env.values())
        info=c.inspect(svc,{})
        self.assertTrue(info['account_enabled'] and info['marketing_enabled'])
        for key,value in (
            ('RICHON_MARKETING_CONSENT_ENABLED','false'),
            ('RICHON_ACCOUNT_ENABLED','false'),
            ('RICHON_TERMS_VERSION','internal-test-v1'),
        ):
            bad=deepcopy(svc)
            bad_env=c.environment(bad['spec']['template']['spec']['containers'][0])
            bad_env[key]['value']=value
            bad['spec']['template']['spec']['containers'][0]['env']=list(bad_env.values())
            with self.subTest(key=key), self.assertRaises(c.Stop):
                c.inspect(bad,{})

    def test_internal_update_preserves_existing_secret_references(self):
        svc = service(); changed = c.intended(svc, 'configure-internal-login')
        self.assertFalse(c.inspect(svc, {})['enabled'])
        self.assertTrue(c.inspect(changed, {})['enabled'])
        before = c.environment(svc['spec']['template']['spec']['containers'][0])
        after = c.environment(changed['spec']['template']['spec']['containers'][0])
        for key in c.SECRET_NAMES: self.assertEqual(before[key], after[key])

    def test_candidate_preserves_traffic_and_configuration(self):
        for operation in ('deploy', 'configure-internal-login'):
            state, svc = candidate_state(operation)
            self.assertIn(c.TAG + '---', op.verify_candidate(state, svc, {}))

    def test_candidate_cannot_change_security_or_secrets(self):
        for mutate in (
            lambda s: s['metadata']['annotations'].update({'run.googleapis.com/ingress': 'internal'}),
            lambda s: s['spec']['template']['spec']['containers'][0]['env'][-1]['valueFrom']['secretKeyRef'].update({'key': '2'}),
            lambda s: s['status']['traffic'][0].update({'percent': 50}),
            lambda s: s['status'].update({'latestCreatedRevisionName': c.SERVICE + '-someone-else'}),
        ):
            state, svc = candidate_state(); mutate(svc)
            with self.assertRaises(c.Stop): op.verify_candidate(state, svc, {})

    def test_bad_candidate_redirect_target_rejected(self):
        for url in ('https://evil.invalid', c.URL + '/path', c.URL + '?token=x', c.URL.replace('https:', 'http:')):
            state, svc = candidate_state(); svc['status']['traffic'][-1]['url'] = url
            with self.assertRaises(c.Stop): op.verify_candidate(state, svc, {})

    def test_iam_mutation_rejected(self):
        state, svc = candidate_state()
        with self.assertRaises(c.Stop): op.verify_candidate(state, svc, {'bindings': [{'role': 'roles/run.invoker', 'members': ['user:other@example.invalid']}]})

    def test_policy_order_does_not_look_like_mutation(self):
        first = {'etag': 'a', 'bindings': [{'role': 'roles/run.invoker', 'members': ['b', 'a']}]}
        second = {'etag': 'b', 'bindings': [{'role': 'roles/run.invoker', 'members': ['a', 'b']}]}
        self.assertEqual(c.policy_key(first), c.policy_key(second))


class TransportTests(unittest.TestCase):
    def test_subprocess_errors_never_reveal_values(self):
        for raw, code in [(b'PRIVATE SECRET permission denied', 'permission_denied'), (b'PRIVATE active account', 'auth_required'), (b'PRIVATE url', 'command_failed')]:
            fake = subprocess.CompletedProcess([], 1, b'PRIVATE', raw)
            with patch.object(c.subprocess, 'run', return_value=fake):
                with self.assertRaises(c.Stop) as result: c.command(['gcloud', 'x'])
                self.assertEqual(str(result.exception), code)

    def test_subprocess_timeout_sanitized(self):
        with patch.object(c.subprocess, 'run', side_effect=subprocess.TimeoutExpired('SECRET', 1)):
            with self.assertRaisesRegex(c.Stop, 'command_timeout'): c.command(['x'])

    def test_bad_cloud_json_sanitized(self):
        with patch.object(c, 'command', return_value='PRIVATE'):
            with self.assertRaisesRegex(c.Stop, 'invalid_cloud_response'): c.gc('x')

    def test_redirects_never_followed(self):
        self.assertIsNone(op.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid'))

    def test_probe_never_sends_token_to_foreign_host(self):
        with patch.object(op.urllib.request, 'build_opener') as build:
            with self.assertRaisesRegex(c.Stop, 'unsafe_probe_url'): op.probe('https://evil.invalid', True)
            build.assert_not_called()

    def test_probe_requires_id_token(self):
        with patch.dict(os.environ, {'PORTAL_ID_TOKEN': ''}):
            with self.assertRaisesRegex(c.Stop, 'id_token_missing'): op.probe(c.URL, True)

    def test_probe_only_auth_header_no_cookies_and_returns_no_raw_body(self):
        response = Mock(); response.code = 403; response.headers = {'Content-Type': 'application/json'}
        response.read.return_value = b'{"detail":"edge_required"}'
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        opener = Mock(); opener.open.return_value = response
        with patch.dict(os.environ, {'PORTAL_ID_TOKEN': 'aaa.bbb.ccc'}), patch.object(op.urllib.request, 'build_opener', return_value=opener):
            op.probe(c.URL, True)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, c.URL + '/auth/login')
        self.assertEqual(dict(request.header_items()), {'Authorization': 'Bearer aaa.bbb.ccc'})
        self.assertIsNone(request.data)

    def test_probe_rejects_html_or_unexpected_success(self):
        response = Mock(); response.code = 200; response.headers = {'Content-Type': 'text/html'}
        response.read.return_value = b'SECRET'
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        opener = Mock(); opener.open.return_value = response
        with patch.dict(os.environ, {'PORTAL_ID_TOKEN': 'aaa.bbb.ccc'}), patch.object(op.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(c.Stop) as result: op.probe(c.URL, True)
        self.assertNotIn('SECRET', str(result.exception))


class ConnectionTests(unittest.TestCase):
    def test_exact_provider_trust(self):
        value = {'attributeMapping': c.MAPPING, 'attributeCondition': c.CONDITION,
                 'oidc': {'issuerUri': 'https://token.actions.githubusercontent.com'}}
        self.assertTrue(connect.provider_matches(value))
        for key in ('repository_id', 'repository_owner_id', 'ref', 'workflow_ref', 'event_name'):
            changed = deepcopy(value); changed['attributeCondition'] = c.CONDITION.replace('assertion.' + key, 'missing.' + key)
            self.assertFalse(connect.provider_matches(changed))

    def test_extra_audiences_rejected(self):
        value = {'attributeMapping': c.MAPPING, 'attributeCondition': c.CONDITION,
                 'oidc': {'issuerUri': 'https://token.actions.githubusercontent.com', 'allowedAudiences': ['other']}}
        self.assertFalse(connect.provider_matches(value))

    def test_existing_excess_grant_not_adopted(self):
        with self.assertRaises(c.Stop):
            connect.member_grants({'bindings': [{'role': 'roles/owner', 'members': ['target']}]}, 'target', {'roles/run.invoker'})

    def test_cancel_has_no_cloud_writes(self):
        def gc(*args, **kwargs):
            self.assertFalse(any(x in args for x in ('create', 'create-oidc', 'enable', 'add-iam-policy-binding')))
            if args[:2] == ('auth', 'list'): return [{'status': 'ACTIVE'}]
            if args[:2] == ('projects', 'describe'): return {'projectNumber': c.NUMBER}
            if args[:3] == ('artifacts', 'repositories', 'describe'):
                return {'format': 'DOCKER', 'labels': {'managed-by': 'richon-portal-bootstrap-v1'}}
            return {}
        with patch.object(c, 'source'), patch.object(c, 'gc', side_effect=gc), patch.object(c, 'get_service', return_value=(service(), {})), patch.object(connect, 'old_connection', return_value=[]), patch('builtins.input', return_value='NO'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(connect.setup(), 0)

    def test_binding_retry_is_bounded(self):
        with patch.object(c, 'gc', side_effect=c.Stop('permission_denied')) as call, patch.object(connect.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(c.Stop): connect.bind(['run', 'services'], c.SERVICE, 'member', 'role')
            self.assertEqual(call.call_count, 6)

    def test_hold_request_is_valid(self):
        self.assertEqual(c.read_request({'operation': 'hold', 'request_id': 'initial-connection-pending'})['operation'], 'hold')

    def test_no_runtime_or_secret_or_public_mutations_in_operations(self):
        text = (Path(__file__).parent / 'operate.py').read_text()
        for forbidden in ('allow-unauthenticated', '--no-invoker-iam-check', 'set-iam-policy', '--update-secrets', 'versions\', \'access', 'run_sql', 'psycopg'):
            self.assertNotIn(forbidden, text)

    def test_workflow_builds_before_auth_and_uses_only_pinned_actions(self):
        text = (c.ROOT / '.github/workflows/portal-deploy.yml').read_text()
        self.assertLess(text.index('docker build'), text.index('uses: google-github-actions/auth@'))
        import re
        for sha in re.findall(r'uses: [^@\s]+@([^\s]+)', text): self.assertRegex(sha, '^[a-f0-9]{40}$')
        self.assertIn("paths: ['.github/portal-deploy.request']", text)
        self.assertNotIn('pull_request_target', text)
        self.assertNotIn('credentials_json', text)


class OperationTests(unittest.TestCase):
    def context(self, sha='a'*40):
        return {'GITHUB_REPOSITORY': c.REPO, 'GITHUB_REPOSITORY_ID': c.REPO_ID,
                'GITHUB_REPOSITORY_OWNER_ID': c.OWNER_ID, 'GITHUB_REF': c.REF,
                'GITHUB_WORKFLOW_REF': c.WORKFLOW, 'GITHUB_EVENT_NAME': 'push',
                'GITHUB_SHA': sha, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}

    def git(self, args, **kwargs):
        if args[1:3] == ['rev-parse', 'HEAD']: return 'a'*40
        if args[1] == 'ls-remote': return 'a'*40 + '\t' + c.REF
        return ''

    def test_current_trusted_source_passes(self):
        with patch.dict(os.environ, self.context()), patch.object(c, 'command', side_effect=self.git):
            self.assertEqual(c.source(live=True), 'a'*40)

    def test_untrusted_workflow_context_blocks(self):
        for field in ('GITHUB_EVENT_NAME', 'GITHUB_REPOSITORY_ID', 'GITHUB_REPOSITORY_OWNER_ID', 'GITHUB_REF', 'GITHUB_WORKFLOW_REF'):
            env = self.context(); env[field] = 'untrusted'
            with patch.dict(os.environ, env), patch.object(c, 'command', side_effect=self.git):
                with self.assertRaisesRegex(c.Stop, 'untrusted_workflow_context'): c.source(live=True)

    def test_stale_source_blocks_even_valid_oidc_branch(self):
        def git(args, **kwargs):
            return 'b'*40 + '\t' + c.REF if args[1] == 'ls-remote' else self.git(args)
        with patch.dict(os.environ, self.context()), patch.object(c, 'command', side_effect=git):
            with self.assertRaisesRegex(c.Stop, 'stale_request_commit'): c.source(live=True)

    def test_state_is_private_and_bound_to_request_run(self):
        request = {'operation': 'inspect', 'request_id': 'test'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**self.context(), 'RUNNER_TEMP': tmp}), patch.object(c, 'read_request', return_value=request):
            op.save({'sha': 'a'*40, 'run': '123', 'attempt': '1', 'request': request})
            self.assertEqual(op.state_path().stat().st_mode & 0o777, 0o600)
            self.assertEqual(op.load()['run'], '123')
            with patch.dict(os.environ, {'GITHUB_RUN_ATTEMPT': '2'}):
                with self.assertRaisesRegex(c.Stop, 'stale_operation_state'): op.load()

    def test_snapshot_hold_never_contacts_gcp(self):
        with patch.object(c, 'source', return_value='a'*40), patch.object(c, 'read_request', return_value={'operation': 'hold', 'request_id': 'x'}), patch.object(c, 'get_service') as get:
            with self.assertRaisesRegex(c.Stop, 'no_operation_requested'): op.snapshot()
            get.assert_not_called()

    def test_inspect_is_read_only(self):
        svc = service(); state = {'request': {'operation': 'inspect'}, 'before': svc, 'policy': {}}
        with patch.object(op, 'load', return_value=state), patch.object(c, 'get_service', return_value=(svc, {})), patch.object(op, 'probe') as probe, patch.object(c, 'gc') as gc, contextlib.redirect_stdout(io.StringIO()):
            op.inspect_existing()
            self.assertEqual(probe.call_count, 2)
            gc.assert_not_called()

    def test_failed_candidate_does_not_promote(self):
        state, svc = candidate_state()
        with patch.object(op, 'load', return_value=state), patch.object(c, 'source'), patch.object(c, 'get_service', return_value=(svc, {})), patch.object(op, 'probe', side_effect=c.Stop('origin_boundary_probe_failed')), patch.object(c, 'gc') as gc:
            with self.assertRaises(c.Stop): op.promote()
            gc.assert_not_called()

    def test_concurrent_edit_after_probe_does_not_promote(self):
        state, svc = candidate_state(); changed=deepcopy(svc)
        changed['status']['latestCreatedRevisionName']=c.SERVICE+'-someone-else'
        with patch.object(op, 'load', return_value=state), patch.object(c, 'source'), patch.object(c, 'get_service', side_effect=[(svc, {}), (changed, {})]), patch.object(op, 'probe'), patch.object(c, 'gc') as gc:
            with self.assertRaises(c.Stop): op.promote()
            gc.assert_not_called()

    def test_verified_promotion_only_changes_target_traffic(self):
        state, svc = candidate_state('configure-internal-login'); final=deepcopy(svc)
        final['status']['traffic']=[{'revisionName':state['candidate'],'percent':100}]
        with patch.object(op, 'load', return_value=state), patch.object(c, 'source'), patch.object(c, 'get_service', side_effect=[(svc, {}), (svc, {}), (final, {})]), patch.object(op, 'probe') as probe, patch.object(c, 'gc') as gc, contextlib.redirect_stdout(io.StringIO()):
            op.promote()
            gc.assert_called_once_with('run','services','update-traffic',c.SERVICE,'--region='+c.REGION,'--to-revisions='+state['candidate']+'=100','--remove-tags='+c.TAG,timeout=180)
            self.assertEqual(probe.call_count, 4)


if __name__ == '__main__':
    unittest.main()
