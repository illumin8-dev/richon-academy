"""Offline guards for canonical course-domain candidate staging."""
from copy import deepcopy
from unittest import TestCase

import common as c
import course_stage as course
from test_marketing_stage import marketing_fixture


def course_before():
    before,policy,current,_,_,new_rev,_,_=marketing_fixture(switched=True)
    # The marketing fixture's switched state is a valid account+marketing worker candidate.
    current['spec']['traffic']=[{k:v for k,v in row.items() if k!='url'}
                               for row in current['status']['traffic']]
    return deepcopy(current),policy,new_rev


class CourseStageTests(TestCase):
    def test_request_contract_accepts_only_explicit_course_operations(self):
        self.assertEqual(c.read_request({
            'operation':'stage-course-enabled','request_id':'course-test-a'
        })['operation'],'stage-course-enabled')
        self.assertEqual(c.read_request({
            'operation':'inspect-course-enabled','request_id':'course-test-b'
        })['operation'],'inspect-course-enabled')

    def test_intended_adds_only_course_flag(self):
        before,policy,_=course_before()
        original=deepcopy(before)
        changed=course.intended(before)
        env=c.environment(changed['spec']['template']['spec']['containers'][0])
        self.assertEqual(env['RICHON_COURSE_DOMAIN_ENABLED']['value'],'true')
        self.assertNotIn('RICHON_COURSE_DOMAIN_ENABLED',
                         c.environment(original['spec']['template']['spec']['containers'][0]))
        info=c.inspect(changed,policy,boundary='edge')
        self.assertTrue(info['account_enabled'])
        self.assertTrue(info['marketing_enabled'])
        self.assertTrue(info['course_enabled'])
        changed_env=deepcopy(changed)
        changed_env['spec']['template']['spec']['containers'][0]['env']=[
            row for row in changed_env['spec']['template']['spec']['containers'][0]['env']
            if row['name']!='RICHON_COURSE_DOMAIN_ENABLED'
        ]
        self.assertEqual(c.protected(changed_env),c.protected(original))

    def test_tag_switch_changes_only_worker_candidate(self):
        before,_,_=course_before()
        new_rev=c.SERVICE+'-course-123-1'
        expected=[]
        for tag,revision,percent,url in course.tag_rows(before):
            expected.append((tag,new_rev if tag==c.TAG else revision,percent,url))
        self.assertEqual(course.expected_switched(before,new_rev),sorted(expected))

    def test_course_requires_account(self):
        before,policy,_=course_before()
        changed=course.intended(before)
        env=c.environment(changed['spec']['template']['spec']['containers'][0])
        env.pop('RICHON_ACCOUNT_ENABLED')
        changed['spec']['template']['spec']['containers'][0]['env']=list(env.values())
        with self.assertRaises(c.Stop):
            c.inspect(changed,policy,boundary='edge')


if __name__=='__main__':
    import unittest
    unittest.main()
