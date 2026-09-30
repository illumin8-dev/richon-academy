"""Offline guards for monthly/manual protected-candidate staging."""
from copy import deepcopy
from unittest import TestCase

import common as c
import legacy_admin_stage as legacy
from test_course_stage import course_before


class LegacyAdminStageTests(TestCase):
    def test_request_contract_accepts_only_explicit_legacy_operations(self):
        self.assertEqual(c.read_request({
            'operation':'stage-legacy-admin-enabled','request_id':'legacy-test-a'
        })['operation'],'stage-legacy-admin-enabled')
        self.assertEqual(c.read_request({
            'operation':'inspect-legacy-admin-enabled','request_id':'legacy-test-b'
        })['operation'],'inspect-legacy-admin-enabled')

    def test_intended_changes_only_monthly_manual_flags(self):
        before,policy,_=course_before()
        # The course fixture has account+marketing+course enabled and legacy OFF.
        original=deepcopy(before)
        changed=legacy.intended(before)
        env=c.environment(changed['spec']['template']['spec']['containers'][0])
        self.assertEqual(env['RICHON_MONTHLY_ENABLED']['value'],'true')
        self.assertEqual(env['RICHON_MANUAL_ENABLED']['value'],'true')
        info=c.inspect(changed,policy,boundary='edge')
        self.assertTrue(info['account_enabled'])
        self.assertTrue(info['marketing_enabled'])
        self.assertTrue(info['course_enabled'])
        self.assertTrue(info['monthly_enabled'])
        self.assertTrue(info['manual_enabled'])

        restored=deepcopy(changed)
        restored_env=c.environment(restored['spec']['template']['spec']['containers'][0])
        restored_env['RICHON_MONTHLY_ENABLED']['value']='false'
        restored_env['RICHON_MANUAL_ENABLED']['value']='false'
        restored['spec']['template']['spec']['containers'][0]['env']=list(restored_env.values())
        self.assertEqual(c.protected(restored),c.protected(original))

    def test_partial_legacy_enablement_is_rejected(self):
        before,policy,_=course_before()
        env=c.environment(before['spec']['template']['spec']['containers'][0])
        env['RICHON_MONTHLY_ENABLED']['value']='true'
        env['RICHON_MANUAL_ENABLED']['value']='false'
        before['spec']['template']['spec']['containers'][0]['env']=list(env.values())
        with self.assertRaises(c.Stop):
            c.inspect(before,policy,boundary='edge')

    def test_tag_switch_changes_only_worker_candidate(self):
        before,_,_=course_before()
        new_rev=c.SERVICE+'-legacy-123-1'
        expected=[]
        for tag,revision,percent,url in legacy.tag_rows(before):
            expected.append((tag,new_rev if tag==c.TAG else revision,percent,
                             legacy.e.CANDIDATE if tag==c.TAG else url))
        self.assertEqual(legacy.expected_switched(before,new_rev),sorted(expected))


if __name__=='__main__':
    import unittest
    unittest.main()
