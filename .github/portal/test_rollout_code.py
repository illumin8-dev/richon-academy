"""Synthetic-only regression tests for the code-only deployment procedure."""
from copy import deepcopy
from contextlib import ExitStack
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import common as c
import edge_ops as e
import candidate_readback as r
import rollout_code as d
from test_candidate_readback import fixture


def state_and_candidate(switched=False):
    before, policy, _ = fixture()
    state = {'before': before, 'policy': policy, 'image': c.IMAGE+'@sha256:'+'c'*64,
             'candidate': c.SERVICE+'-gh-456-1'}
    svc = deepcopy(before)
    svc['spec']['template']['spec']['containers'][0]['image'] = state['image']
    svc['status'].update(latestCreatedRevisionName=state['candidate'], latestReadyRevisionName=state['candidate'])
    if switched:
        svc['status']['traffic'][1]['revisionName'] = state['candidate']
    else:
        svc['status']['traffic'].append({'tag':d.CHECK_TAG,'revisionName':state['candidate'],'url':d.CHECK_URL})
    svc['spec']['traffic'] = [{k:v for k,v in x.items() if k!='url'} for x in svc['status']['traffic']]
    return state, svc, policy


class CodeRollout(TestCase):
    def test_new_operation_is_explicit_not_an_enable_or_migration(self):
        self.assertEqual(c.read_request({'operation':'rollout-edge-code','request_id':'test'})['operation'],'rollout-edge-code')
        for name in ('activate-member-info','migrate','publish-policy'):
            with self.assertRaises(c.Stop): c.read_request({'operation':name,'request_id':'test'})

    def test_check_stage_and_switched_state_are_distinct(self):
        for switched in (False,True):
            state,svc,policy=state_and_candidate(switched)
            d.verify_new(state,svc,policy,switched=switched)
            with self.assertRaises(c.Stop): d.verify_new(state,svc,policy,switched=not switched)

    def test_all_protected_configuration_is_unchanged(self):
        mutations=[lambda x:x['spec']['template']['spec'].update(timeoutSeconds=61),
                   lambda x:x['spec']['template']['spec']['containers'][0]['env'].append({'name':'UNREVIEWED','value':'1'}),
                   lambda x:x['metadata']['annotations'].update({'run.googleapis.com/ingress':'internal'}),
                   lambda x:x['spec']['template']['spec']['containers'][0].update(image=c.IMAGE+':latest'),
                   lambda x:x['status'].update(latestReadyRevisionName=r.CANDIDATE)]
        for mutate in mutations:
            state,svc,policy=state_and_candidate();mutate(svc)
            with self.assertRaises(c.Stop): d.verify_new(state,svc,policy)

    def test_member_info_cannot_be_enabled_by_code_rollout(self):
        for key in ('RICHON_TERMS_VERSION','RICHON_PRIVACY_VERSION'):
            state,svc,policy=state_and_candidate()
            for item in svc['spec']['template']['spec']['containers'][0]['env']:
                if item['name']==key:item['value']='member-info-v1'
            with self.assertRaises(c.Stop):d.verify_new(state,svc,policy)

    def test_wrong_tags_urls_percentages_and_latest_are_rejected(self):
        mutations=[lambda x:x['status']['traffic'][1].update(revisionName='wrong'),
                   lambda x:x['status']['traffic'][2].update(url='https://evil.invalid'),
                   lambda x:x['status']['traffic'][2].update(percent=1),
                   lambda x:x['status']['traffic'].append({'revisionName':'other'}),
                   lambda x:x['spec']['traffic'][0].update(latestRevision=True),
                   lambda x:x['spec']['traffic'][1].update(revisionName='wrong')]
        for mutate in mutations:
            state,svc,policy=state_and_candidate();mutate(svc)
            with self.assertRaises(c.Stop):d.verify_new(state,svc,policy)

    def test_changed_iam_rejected(self):
        state,svc,policy=state_and_candidate(); changed=deepcopy(policy)
        changed['bindings'][0]['members'].append('serviceAccount:unknown@example.invalid')
        with self.assertRaises(c.Stop):d.verify_new(state,svc,changed)

    def test_immutable_revision_name_ready_and_spec_checked(self):
        state,svc,policy=state_and_candidate()
        rev={'metadata':{'name':state['candidate'],'namespace':c.NUMBER,
             'labels':{'serving.knative.dev/service':c.SERVICE},
             'annotations':deepcopy(svc['spec']['template']['metadata']['annotations'])},
             'spec':deepcopy(svc['spec']['template']['spec']),
             'status':{'conditions':[{'type':'Ready','status':'True'}]}}
        with patch.object(c,'gc',return_value=rev):d.verify_new_revision(state,svc,policy)
        for mutate in (lambda x:x['metadata'].update(name='wrong'),
                       lambda x:x['status'].update(conditions=[]),
                       lambda x:x['spec']['containers'][0].update(command=['sh'])):
            bad=deepcopy(rev);mutate(bad)
            with patch.object(c,'gc',return_value=bad),self.assertRaises(c.Stop):d.verify_new_revision(state,svc,policy)

    def test_exact_observed_container_name_pair_only(self):
        state,svc,policy=state_and_candidate()
        rev={'metadata':{'name':state['candidate'],'namespace':c.NUMBER,
             'labels':{'serving.knative.dev/service':c.SERVICE},
             'annotations':deepcopy(svc['spec']['template']['metadata']['annotations'])},
             'spec':deepcopy(svc['spec']['template']['spec']),
             'status':{'conditions':[{'type':'Ready','status':'True'}]}}
        rev['spec']['containers'][0]['name']='portal-1'
        with patch.object(c,'gc',return_value=rev):d.verify_new_revision(state,svc,policy)
        rev['spec']['containers'][0]['name']='other'
        with patch.object(c,'gc',return_value=rev),self.assertRaises(c.Stop):d.verify_new_revision(state,svc,policy)

    def test_unapproved_operation_stops_before_cloud_or_image_upload(self):
        with patch.object(c,'source',return_value='a'*40),patch.object(c,'read_request',return_value={'operation':'stage-edge'}),patch.object(c,'gc') as cloud,patch.object(c,'command') as cmd:
            with self.assertRaises(c.Stop):d.run()
            cloud.assert_not_called();cmd.assert_not_called()

    def test_fixed_check_url_missing_and_wrong_keys_only(self):
        class Response:
            code=403;headers={'Content-Type':'application/json'}
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return b'{"detail":"edge_required"}'
        calls=[]
        class Opener:
            def open(self,req,timeout):calls.append(req);return Response()
        with patch.object(d.urllib.request,'build_opener',return_value=Opener()):d.probe_check_tag()
        self.assertEqual(len(calls),2)
        for req in calls:
            self.assertEqual(req.full_url,d.CHECK_URL+'/auth/login');self.assertEqual(req.get_method(),'GET')
            self.assertIsNone(req.get_header('Authorization'));self.assertIsNone(req.get_header('Cookie'))
        self.assertIsNone(calls[0].get_header('X-richon-edge-key'))
        self.assertEqual(calls[1].get_header('X-richon-edge-key'),'deliberately-invalid-test-key')

    def test_code_workflow_build_and_dispatch_paths(self):
        text=(Path(__file__).parents[1]/'workflows/portal-deploy.yml').read_text()
        self.assertIn('python3 -B .github/portal/rollout_code.py',text)
        self.assertIn('["deploy","stage-edge","stage-edge-naver","rollout-edge-code","stage-account-code"]',text)
        self.assertIn('["inspect-edge","stage-edge","stage-edge-naver","rollout-edge-code","stage-account-code"]',text)
        self.assertNotIn('secrets versions access',text)

    def test_full_mocked_run_two_narrow_writes_and_preserves_settings(self):
        before,policy,revs=fixture()
        before['spec']['traffic']=[{k:v for k,v in x.items() if k!='url'} for x in before['status']['traffic']]
        current=deepcopy(before);writes=[];read_count=0
        def get():return deepcopy(current),deepcopy(policy)
        def gc(*args,**kw):
            if args[:4]==('artifacts','docker','images','describe'):
                return {'image_summary':{'digest':'sha256:'+('b' if args[4].endswith(':'+r.SOURCE) else 'c')*64}}
            if args[:3]==('run','revisions','describe'):
                name=args[3]
                if name in revs:return revs[name]
                return {'metadata':{'name':name,'namespace':c.NUMBER,'labels':{'serving.knative.dev/service':c.SERVICE},'annotations':deepcopy(current['spec']['template']['metadata']['annotations'])},'spec':deepcopy(current['spec']['template']['spec']),'status':{'conditions':[{'type':'Ready','status':'True'}]}}
            writes.append(args)
            if args[:3]==('run','services','update'):
                image=next(x.partition('=')[2] for x in args if x.startswith('--image='))
                current['spec']['template']['spec']['containers'][0]['image']=image
                new=c.SERVICE+'-gh-456-1'
                current['status'].update(latestCreatedRevisionName=new,latestReadyRevisionName=new)
                current['status']['traffic'].append({'tag':d.CHECK_TAG,'revisionName':new,'url':d.CHECK_URL})
            elif args[:3]==('run','services','update-traffic'):
                current['status']['traffic']=[current['status']['traffic'][0],{'tag':c.TAG,'revisionName':c.SERVICE+'-gh-456-1','url':e.CANDIDATE}]
            else:raise AssertionError(args)
            current['spec']['traffic']=[{k:v for k,v in x.items() if k!='url'} for x in current['status']['traffic']]
        with ExitStack() as stack:
            for obj,key,value in ((c,'source',lambda **k:'a'*40),(c,'read_request',lambda:{'operation':'rollout-edge-code','request_id':'test'}),(c,'command',lambda *a,**k:''),(c,'gc',gc),(e,'get_service',get),(e,'access_status',lambda:'signin-gateway-confirmed'),(e,'probe_origin',lambda u:None),(d,'probe_check_tag',lambda:None),(op:=d.op,'save',lambda x:None),(op,'summary',lambda x:None)):
                stack.enter_context(patch.object(obj,key,side_effect=value))
            stack.enter_context(patch.dict(os.environ,GITHUB_RUN_ID='456',GITHUB_RUN_ATTEMPT='1'))
            d.run()
        self.assertEqual(len(writes),2)
        self.assertIn('--tag='+d.CHECK_TAG,writes[0]);self.assertIn('--no-traffic',writes[0])
        self.assertIn('--update-tags='+c.TAG+'='+c.SERVICE+'-gh-456-1',writes[1])
        for args in writes:
            self.assertFalse(any(x.startswith(('--update-env','--set-env','--update-secrets','--set-secrets','--to-')) for x in args))
        self.assertEqual(c.traffic(current),[(r.SERVING,100)])
