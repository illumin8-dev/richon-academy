"""Offline guards for account-enabled Worker candidate staging."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

import account_enable_stage as a
import account_stage as code_stage
import candidate_readback as r
import common as c
import edge_ops as e
from test_account_stage import staged_fixture


def enabled_fixture():
    _, policy, staged, code_revision, image, _ = staged_fixture()
    new_revision=c.SERVICE+'-accton-456-1'
    current=a.intended(staged)
    current['status']['latestCreatedRevisionName']=new_revision
    current['status']['latestReadyRevisionName']=new_revision
    current['status']['traffic'].append({
        'revisionName':new_revision,'tag':a.CHECK_TAG,'url':a.CHECK_URL,
    })
    immutable={
        'metadata':{
            'name':new_revision,'namespace':c.NUMBER,
            'labels':{'serving.knative.dev/service':c.SERVICE},
            'annotations':deepcopy(current['spec']['template']['metadata']['annotations']),
        },
        'spec':deepcopy(current['spec']['template']['spec']),
        'status':{'conditions':[{'type':'Ready','status':'True'}]},
    }
    return staged,policy,current,code_revision,new_revision,image,immutable


class AccountEnabledStageTests(TestCase):
    def test_exact_account_policy_pair_is_accepted(self):
        staged,policy,_,_,_,_,_=enabled_fixture()
        changed=a.intended(staged)
        self.assertTrue(c.inspect(changed,policy,boundary='edge')['account_enabled'])
        env=c.environment(changed['spec']['template']['spec']['containers'][0])
        self.assertEqual(env['RICHON_ACCOUNT_ENABLED']['value'],'true')
        self.assertEqual(env['RICHON_TERMS_VERSION']['value'],'member-info-v1')
        self.assertEqual(env['RICHON_PRIVACY_VERSION']['value'],'member-info-v1')

    def test_partial_or_false_account_setting_is_rejected(self):
        staged,policy,_,_,_,_,_=enabled_fixture()
        for key,value in (
            ('RICHON_ACCOUNT_ENABLED','false'),
            ('RICHON_TERMS_VERSION','internal-test-v1'),
            ('RICHON_PRIVACY_VERSION','internal-test-v1'),
        ):
            changed=a.intended(staged)
            env=c.environment(changed['spec']['template']['spec']['containers'][0])
            env[key]['value']=value
            changed['spec']['template']['spec']['containers'][0]['env']=list(env.values())
            with self.subTest(key=key), self.assertRaises(c.Stop):
                c.inspect(changed,policy,boundary='edge')

    def test_before_requires_zero_traffic_code_check_as_latest(self):
        staged,policy,_,code_revision,_,_,_=enabled_fixture()
        with patch.object(code_stage,'verify_revision'),              patch.object(e,'access_status',return_value='signin-gateway-confirmed'):
            found,_=a.validate_before(staged,policy)
        self.assertEqual(found,code_revision)
        broken=deepcopy(staged)
        broken['status']['latestReadyRevisionName']=r.CANDIDATE
        with patch.object(code_stage,'verify_revision'),              patch.object(e,'access_status',return_value='signin-gateway-confirmed'):
            with self.assertRaises(c.Stop):
                a.validate_before(broken,policy)

    def test_staged_and_switched_tags_keep_default_100_percent(self):
        before,policy,current,code_revision,new_revision,_,immutable=enabled_fixture()
        with patch.object(c,'gc',return_value=immutable):
            a.verify_config(before,policy,current,policy,new_revision,code_revision,switched=False)
        self.assertEqual(c.traffic(current),[(r.SERVING,100)])
        switched=deepcopy(current)
        switched['status']['traffic']=[
            row for row in switched['status']['traffic'] if row.get('tag')!=a.CHECK_TAG
        ]
        for row in switched['status']['traffic']:
            if row.get('tag')==c.TAG:
                row['revisionName']=new_revision
        with patch.object(c,'gc',return_value=immutable):
            a.verify_config(before,policy,switched,policy,new_revision,code_revision,switched=True)
        self.assertEqual(c.traffic(switched),[(r.SERVING,100)])


    def test_readback_is_read_only_and_confirms_worker_candidate(self):
        before,policy,current,code_revision,new_revision,image,_=enabled_fixture()
        switched=deepcopy(current)
        switched['status']['traffic']=[
            row for row in switched['status']['traffic'] if row.get('tag')!=a.CHECK_TAG
        ]
        for row in switched['status']['traffic']:
            if row.get('tag')==c.TAG:
                row['revisionName']=new_revision
        with patch.object(c,'read_request',return_value={'operation':a.READ_OPERATION,'request_id':'test'}), \
             patch.object(e,'get_service',side_effect=[(switched,policy),(switched,policy)]), \
             patch.object(a,'validate_code_check_revision',return_value=image), \
             patch.object(a,'verify_revision') as verify, \
             patch.object(a,'probe_gate') as probe, \
             patch.object(e,'access_status',return_value='signin-gateway-confirmed'), \
             patch.object(a.op,'summary'):
            self.assertEqual(a.inspect_current('a'*40),0)
        verify.assert_called_once_with(new_revision,switched,policy)
        probe.assert_called_once_with(e.CANDIDATE)

    def test_readback_section_contains_no_cloud_write(self):
        source=(c.ROOT/'.github/portal/account_enable_stage.py').read_text()
        section=source[source.index('def inspect_current'):source.index('def run():')]
        self.assertNotIn("services','update",section)
        self.assertNotIn('update-traffic',section)
        self.assertNotIn('unlink_access',section)
        workflow=(c.ROOT/'.github/workflows/portal-deploy.yml').read_text()
        self.assertIn('"inspect-account-enabled"',workflow)
        self.assertGreaterEqual(workflow.count('"inspect-account-enabled"'),4)

    def test_operation_is_explicit_and_never_promotes_default_traffic(self):
        self.assertEqual(c.read_request({'operation':a.OPERATION,'request_id':'test'})['operation'],a.OPERATION)
        self.assertEqual(c.read_request({'operation':a.READ_OPERATION,'request_id':'test'})['operation'],a.READ_OPERATION)
        workflow=(c.ROOT/'.github/workflows/portal-deploy.yml').read_text()
        self.assertIn('"stage-account-enabled"',workflow)
        self.assertIn('python3 -B .github/portal/account_enable_stage.py',workflow)
        source=(c.ROOT/'.github/portal/account_enable_stage.py').read_text()
        self.assertNotIn('--to-revisions=',source)
        self.assertIn("'--update-tags='+c.TAG+'='+revision",source)
        self.assertIn('DEFAULT TRAFFIC UNCHANGED',source)

    def test_operation_has_no_db_or_provider_api_client(self):
        source=(c.ROOT/'.github/portal/account_enable_stage.py').read_text().lower()
        for forbidden in ('run_sql','psycopg','api.cloudflare.com','kapi.kakao.com','nid.naver.com/oauth2.0/revoke'):
            self.assertNotIn(forbidden,source)
