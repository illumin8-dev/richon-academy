"""Offline tests for the exact existing candidate; no cloud or credentials."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
import common as c
import edge_ops as e
import candidate_readback as r
from test_automation import service
from test_edge_ops import public_policy


def fixture():
    old = service(True)
    svc = e.candidate_configuration(old, 'stage-edge-naver')
    svc['spec']['template']['spec']['containers'][0]['image'] = c.IMAGE + '@sha256:' + 'b' * 64
    svc['status'].update(latestCreatedRevisionName=r.CANDIDATE, latestReadyRevisionName=r.CANDIDATE,
                         traffic=[{'revisionName': r.SERVING, 'percent': 100},
                                  {'revisionName': r.CANDIDATE, 'tag': c.TAG, 'url': e.CANDIDATE}])
    revisions = {}
    for name, src in ((r.CANDIDATE, svc), (r.SERVING, old)):
        revisions[name] = {'metadata': {'name': name, 'namespace': c.NUMBER,
            'labels': {'serving.knative.dev/service': c.SERVICE},
            'annotations': deepcopy(src['spec']['template']['metadata']['annotations'])},
            'spec': deepcopy(src['spec']['template']['spec']),
            'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}
    return svc, public_policy(), revisions


class CandidateReadback(TestCase):
    def test_exact_candidate_and_two_revision_specs(self):
        svc, policy, revisions = fixture(); original = deepcopy(svc)
        self.assertEqual(r.validate_service(svc, policy)['revision'], r.CANDIDATE)
        for name, rev in revisions.items(): r.validate_revision(rev, name, svc, policy)
        self.assertEqual(svc, original)

    def test_unknown_candidate_tag_traffic_or_versions_fail(self):
        mutations = [
            lambda x: x['status'].update(latestCreatedRevisionName='other', latestReadyRevisionName='other'),
            lambda x: x['status']['traffic'][0].update(percent=99),
            lambda x: x['status']['traffic'][1].update(tag='other'),
            lambda x: x['status']['traffic'][1].update(revisionName=r.SERVING),
            lambda x: x['status']['traffic'][1].update(percent=1),
            lambda x: x['status']['traffic'][1].update(url='https://evil.invalid/'),
            lambda x: x['status']['traffic'].append({'revisionName': 'other', 'percent': 0}),
            lambda x: x['spec']['template']['spec']['containers'][0]['env'][-1]['valueFrom']['secretKeyRef'].update(key='2'),
        ]
        for mutate in mutations:
            svc, policy, _ = fixture(); mutate(svc)
            with self.assertRaises(c.Stop): r.validate_service(svc, policy)

    def test_revision_identity_ready_and_runtime_are_required(self):
        mutations = [lambda x: x['metadata'].update(namespace='other'),
                     lambda x: x['metadata'].update(name=r.SERVING),
                     lambda x: x['metadata']['labels'].update({'serving.knative.dev/service': 'other'}),
                     lambda x: x['status'].update(conditions=[]),
                     lambda x: x['spec'].update(serviceAccountName='other'),
                     lambda x: x['spec']['containers'][0].update(command=['sh'])]
        for mutate in mutations:
            svc, policy, revisions = fixture(); rev = revisions[r.CANDIDATE]; mutate(rev)
            with self.assertRaises(c.Stop): r.validate_revision(rev, r.CANDIDATE, svc, policy)

    def test_candidate_image_and_rollback_bindings_must_match(self):
        svc, policy, revs = fixture()
        revs[r.CANDIDATE]['spec']['containers'][0]['image'] = c.IMAGE + '@sha256:' + 'c' * 64
        with self.assertRaises(c.Stop): r.validate_revision(revs[r.CANDIDATE], r.CANDIDATE, svc, policy)
        revs[r.SERVING]['spec'] = deepcopy(svc['spec']['template']['spec'])
        with self.assertRaises(c.Stop): r.validate_revision(revs[r.SERVING], r.SERVING, svc, policy)

    def test_real_execution_uses_only_fixed_describe_calls(self):
        svc, policy, revisions = fixture(); calls = []
        def gc(*args, **kwargs):
            calls.append(args)
            if args[:3] == ('run', 'revisions', 'describe'): return revisions[args[3]]
            self.assertEqual(args, ('artifacts', 'docker', 'images', 'describe', c.IMAGE + ':' + r.SOURCE))
            return {'image_summary': {'digest': 'sha256:' + 'b' * 64}}
        with patch.object(c, 'read_request', return_value={'operation':'inspect-edge'}), \
             patch.object(c, 'gc', side_effect=gc), patch.object(c, 'command') as commands, \
             patch.object(e, 'access_status', return_value='signin-gateway-confirmed'), \
             patch.object(e, 'probe_origin') as probes, patch.object(e, 'get_service', return_value=(svc, policy)), \
             patch.object(r.op, 'summary') as summary:
            r.inspect_existing(svc, policy)
        self.assertEqual(len(calls), 3); commands.assert_not_called()
        self.assertEqual([call.args[0] for call in probes.call_args_list], [c.URL, e.CANDIDATE])
        self.assertIn('EXISTING CANDIDATE VERIFIED', ' '.join(call.args[0] for call in summary.call_args_list))

    def test_stage_request_cannot_enter_readback(self):
        svc, policy, _ = fixture()
        with patch.object(c, 'read_request', return_value={'operation':'stage-edge-naver'}), patch.object(c, 'gc') as gc:
            with self.assertRaises(c.Stop): r.inspect_existing(svc, policy)
        gc.assert_not_called()

    def test_unmatched_registry_digest_stops_before_network_probe(self):
        svc, policy, revisions = fixture()
        def gc(*args, **kw):
            return revisions[args[3]] if args[:3] == ('run','revisions','describe') else {'image_summary':{'digest':'sha256:'+'c'*64}}
        with patch.object(c, 'read_request', return_value={'operation':'inspect-edge'}), patch.object(c, 'gc', side_effect=gc), patch.object(e, 'access_status') as network:
            with self.assertRaisesRegex(c.Stop, 'candidate_source_image_mismatch'): r.inspect_existing(svc, policy)
        network.assert_not_called()

    def test_main_routes_only_read_only_existing_inspection(self):
        svc, policy, _ = fixture()
        with patch.object(c, 'source') as source, patch.object(c, 'read_request', return_value={'operation':'inspect-edge'}), \
             patch.object(e, 'get_service', return_value=(svc,policy)), patch.object(r, 'inspect_existing') as read, patch.object(e, 'main') as legacy:
            r.main()
        source.assert_called_once_with(live=True); read.assert_called_once_with(svc,policy); legacy.assert_not_called()

    def test_legacy_inspect_without_tag_is_preserved(self):
        svc = service(True)
        with patch.object(c, 'source'), patch.object(c, 'read_request', return_value={'operation':'inspect-edge'}), \
             patch.object(e, 'get_service', return_value=(svc,public_policy())), patch.object(r,'inspect_existing') as read, patch.object(e,'main') as legacy:
            r.main()
        read.assert_not_called(); legacy.assert_called_once()


    def test_serving_origin_failure_is_classified_without_raw_response(self):
        svc, policy, revisions = fixture()
        def gc(*args, **kw):
            return revisions[args[3]] if args[:3] == ('run','revisions','describe') else {'image_summary':{'digest':'sha256:'+'b'*64}}
        def probe(url):
            if url == c.URL:
                raise c.Stop('origin_app_gate_not_confirmed')
        with patch.object(c,'read_request',return_value={'operation':'inspect-edge'}),              patch.object(c,'gc',side_effect=gc), patch.object(e,'access_status',return_value='signin-gateway-confirmed'),              patch.object(e,'probe_origin',side_effect=probe), patch.object(r.op,'summary'):
            with self.assertRaisesRegex(c.Stop,'serving_origin_app_gate_not_confirmed'):
                r.inspect_existing(svc,policy)

    def test_candidate_origin_failure_is_classified_without_raw_response(self):
        svc, policy, revisions = fixture()
        def gc(*args, **kw):
            return revisions[args[3]] if args[:3] == ('run','revisions','describe') else {'image_summary':{'digest':'sha256:'+'b'*64}}
        def probe(url):
            if url == e.CANDIDATE:
                raise c.Stop('origin_app_gate_not_confirmed')
        with patch.object(c,'read_request',return_value={'operation':'inspect-edge'}),              patch.object(c,'gc',side_effect=gc), patch.object(e,'access_status',return_value='signin-gateway-confirmed'),              patch.object(e,'probe_origin',side_effect=probe), patch.object(r.op,'summary'):
            with self.assertRaisesRegex(c.Stop,'candidate_origin_app_gate_not_confirmed'):
                r.inspect_existing(svc,policy)
