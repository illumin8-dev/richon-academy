"""Synthetic-only tests for fail-closed portal candidate recovery."""
from copy import deepcopy
from contextlib import ExitStack
import json
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import common as c
import edge_ops as e
import candidate_readback as r
import candidate_recovery_rollout as d
from test_candidate_readback import fixture


BROKEN='missing-key:503:non_json,wrong-key:500:non_json'


def recovery_fixture():
    svc,policy,revisions=fixture()
    env=c.environment(svc['spec']['template']['spec']['containers'][0])
    env.update({
        'RICHON_ACCOUNT_ENABLED':{'name':'RICHON_ACCOUNT_ENABLED','value':'true'},
        'RICHON_MARKETING_CONSENT_ENABLED':{'name':'RICHON_MARKETING_CONSENT_ENABLED','value':'true'},
        'RICHON_COURSE_DOMAIN_ENABLED':{'name':'RICHON_COURSE_DOMAIN_ENABLED','value':'true'},
        'RICHON_MONTHLY_ENABLED':{'name':'RICHON_MONTHLY_ENABLED','value':'true'},
        'RICHON_MANUAL_ENABLED':{'name':'RICHON_MANUAL_ENABLED','value':'true'},
    })
    env['RICHON_TERMS_VERSION']={'name':'RICHON_TERMS_VERSION','value':'member-info-v1'}
    env['RICHON_PRIVACY_VERSION']={'name':'RICHON_PRIVACY_VERSION','value':'member-info-v1'}
    svc['spec']['template']['spec']['containers'][0]['env']=list(env.values())
    return svc,policy,revisions


class CandidateRecovery(TestCase):
    def test_operation_is_explicit(self):
        self.assertEqual(
            c.read_request({'operation':'recover-candidate-code','request_id':'test'})['operation'],
            'recover-candidate-code')
        for name in ('recover','force-deploy','bypass-candidate'):
            with self.assertRaises(c.Stop):
                c.read_request({'operation':name,'request_id':'test'})

    def test_only_known_broken_candidate_state_can_start_recovery(self):
        svc,policy,_=recovery_fixture()
        with patch.object(e,'access_status',return_value='inconclusive'),              patch.object(r,'safe_origin_observation',return_value=BROKEN):
            old,observation=d.ensure_before(svc,policy)
        self.assertEqual(old,r.CANDIDATE)
        self.assertEqual(observation,BROKEN)

        with patch.object(e,'access_status',return_value=e.CUSTOMER_ROUTES),              patch.object(r,'safe_origin_observation',return_value=BROKEN),              self.assertRaisesRegex(c.Stop,'recovery_requires_broken_customer_routes'):
            d.ensure_before(svc,policy)

        with patch.object(e,'access_status',return_value='inconclusive'),              patch.object(r,'safe_origin_observation',
                          return_value='missing-key:403:edge_required,wrong-key:403:edge_required'),              self.assertRaisesRegex(c.Stop,'recovery_candidate_failure_not_recognized'):
            d.ensure_before(svc,policy)

    def test_probe_gate_requires_exact_edge_required_without_credentials(self):
        class Response:
            code=403
            headers={'Content-Type':'application/json'}
            def __enter__(self): return self
            def __exit__(self,*a): return False
            def read(self,n): return b'{"detail":"edge_required"}'
        calls=[]
        class Opener:
            def open(self,req,timeout):
                calls.append(req)
                return Response()
        with patch.object(d.urllib.request,'build_opener',return_value=Opener()):
            d.probe_gate(d.CHECK_URL)
        self.assertEqual(len(calls),2)
        for req in calls:
            self.assertEqual(req.full_url,d.CHECK_URL+'/auth/login')
            self.assertEqual(req.get_method(),'GET')
            self.assertIsNone(req.get_header('Authorization'))
            self.assertIsNone(req.get_header('Cookie'))
        self.assertIsNone(calls[0].get_header('X-richon-edge-key'))
        self.assertEqual(calls[1].get_header('X-richon-edge-key'),
                         'deliberately-invalid-test-key')

    def test_unapproved_operation_stops_before_cloud_or_image_upload(self):
        with patch.object(c,'source',return_value='a'*40),              patch.object(c,'read_request',return_value={'operation':'rollout-login-handoff'}),              patch.object(e,'get_service') as cloud, patch.object(c,'command') as command:
            with self.assertRaises(c.Stop):
                d.run()
            cloud.assert_not_called()
            command.assert_not_called()

    def test_full_recovery_has_only_two_cloud_run_writes(self):
        before,policy,_=recovery_fixture()
        current=deepcopy(before)
        writes=[]

        def get_service():
            return deepcopy(current),deepcopy(policy)

        def gc(*args,**kwargs):
            if args[:4]==('artifacts','docker','images','describe'):
                return {'image_summary':{'digest':'sha256:'+'c'*64}}
            if args[:3]==('run','revisions','describe'):
                name=args[3]
                return {
                    'metadata':{
                        'name':name,'namespace':c.NUMBER,
                        'labels':{'serving.knative.dev/service':c.SERVICE},
                        'annotations':deepcopy(current['spec']['template']['metadata']['annotations']),
                    },
                    'spec':deepcopy(current['spec']['template']['spec']),
                    'status':{'conditions':[{'type':'Ready','status':'True'}]},
                }
            writes.append(args)
            if args[:3]==('run','services','update'):
                image=next(x.partition('=')[2] for x in args if x.startswith('--image='))
                current['spec']['template']['spec']['containers'][0]['image']=image
                new=c.SERVICE+'-recover-456-1'
                current['status'].update(
                    latestCreatedRevisionName=new,latestReadyRevisionName=new)
                current['status']['traffic'].append({
                    'tag':d.CHECK_TAG,'revisionName':new,'url':d.CHECK_URL})
            elif args[:3]==('run','services','update-traffic'):
                new=c.SERVICE+'-recover-456-1'
                current['status']['traffic']=[
                    ({**row,'revisionName':new,'url':e.CANDIDATE}
                     if row.get('tag')==c.TAG else row)
                    for row in current['status']['traffic']
                    if row.get('tag')!=d.CHECK_TAG
                ]
            else:
                raise AssertionError(args)

        with ExitStack() as stack:
            stack.enter_context(patch.object(c,'source',return_value='a'*40))
            stack.enter_context(patch.object(
                c,'read_request',
                return_value={'operation':'recover-candidate-code','request_id':'test'}))
            stack.enter_context(patch.object(c,'command',return_value=''))
            stack.enter_context(patch.object(c,'gc',side_effect=gc))
            stack.enter_context(patch.object(e,'get_service',side_effect=get_service))
            stack.enter_context(patch.object(
                e,'access_status',side_effect=['inconclusive',e.CUSTOMER_ROUTES]))
            stack.enter_context(patch.object(
                r,'safe_origin_observation',return_value=BROKEN))
            stack.enter_context(patch.object(d,'probe_gate'))
            stack.enter_context(patch.object(d.op,'summary'))
            stack.enter_context(patch.dict(
                os.environ,GITHUB_RUN_ID='456',GITHUB_RUN_ATTEMPT='1'))
            d.run()

        self.assertEqual(len(writes),2)
        self.assertIn('--tag='+d.CHECK_TAG,writes[0])
        self.assertIn('--no-traffic',writes[0])
        self.assertIn(
            '--update-tags='+c.TAG+'='+c.SERVICE+'-recover-456-1',writes[1])
        self.assertIn('--remove-tags='+d.CHECK_TAG,writes[1])
        for args in writes:
            self.assertFalse(any(x.startswith(
                ('--update-env','--set-env','--update-secrets','--set-secrets','--to-revisions'))
                for x in args))
        self.assertEqual(c.traffic(current),c.traffic(before))
        self.assertEqual(
            [row['revisionName'] for row in current['status']['traffic']
             if row.get('tag')==c.TAG],
            [c.SERVICE+'-recover-456-1'])

    def test_workflow_has_narrow_recovery_dispatch(self):
        text=(Path(__file__).parents[1]/'workflows/portal-deploy.yml').read_text()
        self.assertIn('python3 -B .github/portal/candidate_recovery_rollout.py',text)
        self.assertIn("needs.request.outputs.operation == 'recover-candidate-code'",text)
        self.assertNotIn('allow-unauthenticated',text)


if __name__=='__main__':
    import unittest
    unittest.main()
