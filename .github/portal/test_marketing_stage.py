"""Offline guards for marketing-enabled protected candidate staging."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

import account_enable_stage as a
import candidate_readback as r
import common as c
import edge_ops as e
import marketing_stage as m
from test_account_enable_stage import enabled_fixture


def before_fixture():
    staged,policy,current,code_rev,account_rev,image,immutable=enabled_fixture()
    before=deepcopy(current)
    before['status']['traffic']=[
        row for row in before['status']['traffic'] if row.get('tag')!=a.CHECK_TAG
    ]
    for row in before['status']['traffic']:
        if row.get('tag')==c.TAG:
            row['revisionName']=account_rev
    before['spec']['traffic']=[{k:v for k,v in row.items() if k!='url'}
                              for row in before['status']['traffic']]
    before['status']['latestCreatedRevisionName']=account_rev
    before['status']['latestReadyRevisionName']=account_rev
    account_immutable=deepcopy(immutable)
    account_immutable['metadata']['name']=account_rev
    return before,policy,code_rev,account_rev,image,account_immutable


def marketing_fixture(switched=False):
    before,policy,code_rev,account_rev,_,_=before_fixture()
    image=c.IMAGE+'@sha256:'+'d'*64
    new_rev=c.SERVICE+'-mkt-789-1'
    current=m.intended_without_policy(before,image)
    current['status']['latestCreatedRevisionName']=new_rev
    current['status']['latestReadyRevisionName']=new_rev
    if switched:
        for row in current['status']['traffic']:
            if row.get('tag')==c.TAG:
                row['revisionName']=new_rev
    else:
        current['status']['traffic'].append({
            'tag':m.CHECK_TAG,'revisionName':new_rev,'url':m.CHECK_URL,
        })
    current['spec']['traffic']=[{k:v for k,v in row.items() if k!='url'}
                               for row in current['status']['traffic']]
    immutable={
        'metadata':{
            'name':new_rev,'namespace':c.NUMBER,
            'labels':{'serving.knative.dev/service':c.SERVICE},
            'annotations':deepcopy(current['spec']['template']['metadata']['annotations']),
        },
        'spec':deepcopy(current['spec']['template']['spec']),
        'status':{'conditions':[{'type':'Ready','status':'True'}]},
    }
    return before,policy,current,code_rev,account_rev,new_rev,image,immutable


class MarketingStageTests(TestCase):
    def test_intended_changes_only_image_and_marketing_flag(self):
        before,policy,_,_,_,_=before_fixture()
        image=c.IMAGE+'@sha256:'+'d'*64
        changed=m.intended_without_policy(before,image)
        info=c.inspect(changed,policy,boundary='edge')
        self.assertTrue(info['account_enabled'])
        self.assertTrue(info['marketing_enabled'])
        env=c.environment(changed['spec']['template']['spec']['containers'][0])
        self.assertEqual(env['RICHON_MARKETING_CONSENT_ENABLED']['value'],'true')
        self.assertEqual(changed['spec']['template']['spec']['containers'][0]['image'],image)
        original=c.environment(before['spec']['template']['spec']['containers'][0])
        self.assertNotIn('RICHON_MARKETING_CONSENT_ENABLED',original)

    def test_before_requires_account_on_marketing_off_and_fixed_tags(self):
        before,policy,code_rev,account_rev,_,_=before_fixture()
        with patch.object(a,'verify_revision'),              patch.object(e,'access_status',return_value='signin-gateway-confirmed'):
            self.assertEqual(m.validate_before(before,policy),(code_rev,account_rev))
        bad=deepcopy(before)
        env=c.environment(bad['spec']['template']['spec']['containers'][0])
        env['RICHON_MARKETING_CONSENT_ENABLED']={'name':'RICHON_MARKETING_CONSENT_ENABLED','value':'true'}
        bad['spec']['template']['spec']['containers'][0]['env']=list(env.values())
        with self.assertRaises(c.Stop):
            m.validate_before(bad,policy)

    def test_zero_percent_stage_and_worker_switch_never_change_default_traffic(self):
        for switched in (False,True):
            before,policy,current,code_rev,account_rev,new_rev,image,immutable=marketing_fixture(switched)
            with patch.object(c,'gc',return_value=immutable):
                m.verify_config(before,policy,current,policy,new_rev,code_rev,account_rev,image,switched=switched)
            self.assertEqual(c.traffic(current),[(r.SERVING,100)])

    def test_operation_is_explicit_and_workflow_builds_then_dispatches(self):
        self.assertEqual(c.read_request({'operation':m.OPERATION,'request_id':'test'})['operation'],m.OPERATION)
        self.assertEqual(c.read_request({'operation':m.READ_OPERATION,'request_id':'test'})['operation'],m.READ_OPERATION)
        workflow=(c.ROOT/'.github/workflows/portal-deploy.yml').read_text()
        self.assertIn('"stage-marketing-enabled"',workflow)
        self.assertIn('"inspect-marketing-enabled"',workflow)
        self.assertIn('python3 -B .github/portal/marketing_stage.py',workflow)
        self.assertLess(workflow.index('Build portal image'),workflow.index('- id: auth'))
        source=(c.ROOT/'.github/portal/marketing_stage.py').read_text()
        self.assertNotIn('--to-revisions=',source)
        self.assertIn("'--update-tags='+c.TAG+'='+revision",source)
        self.assertIn('DEFAULT TRAFFIC UNCHANGED',source)

    def test_operation_does_not_touch_database_iam_secrets_or_provider_apis(self):
        source=(c.ROOT/'.github/portal/marketing_stage.py').read_text().lower()
        for forbidden in ('run_sql','psycopg','set-iam-policy','secrets versions access',
                          'kapi.kakao.com','nid.naver.com/oauth2.0/revoke'):
            self.assertNotIn(forbidden,source)
