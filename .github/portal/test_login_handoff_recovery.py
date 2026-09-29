import inspect
import unittest

import login_handoff_recovery as r


class LoginHandoffRecoveryTests(unittest.TestCase):
    def test_recovery_is_fixed_to_interrupted_run(self):
        self.assertEqual(r.OPERATION, 'recover-login-handoff-check')
        self.assertEqual(r.ORPHAN_REVISION, 'richon-portal-handoff-36609510020-1')
        self.assertEqual(r.EXPECTED_CANDIDATE, 'richon-portal-handoff-36597611986-1')

    def test_recovery_has_one_narrow_cloud_write(self):
        source = inspect.getsource(r.run)
        self.assertIn("'update-traffic'", source)
        self.assertIn("'--remove-tags=' + h.CHECK_TAG", source)
        self.assertNotIn("'--update-tags='", source)
        self.assertNotIn("'--to-revisions='", source)
        self.assertNotIn("'--image='", source)
        self.assertNotIn("'--update-env-vars='", source)
        self.assertNotIn("'--update-secrets='", source)

    def test_preexisting_zero_traffic_tags_are_preserved_by_validation(self):
        svc = {'status': {'traffic': [
            {'revisionName': 'serving-revision', 'percent': 100},
            {'tag': 'portal-candidate', 'revisionName': r.EXPECTED_CANDIDATE,
             'percent': 0, 'url': r.e.CANDIDATE},
            {'tag': r.h.CHECK_TAG, 'revisionName': r.ORPHAN_REVISION,
             'percent': 0, 'url': r.h.CHECK_URL},
            {'tag': 'preexisting-zero-tag', 'revisionName': 'older-zero-revision',
             'percent': 0, 'url': 'https://preexisting-zero-tag.example.invalid'},
        ]}}
        self.assertEqual(r.validate_before_rows(svc), 'serving-revision')
        self.assertIn(('preexisting-zero-tag', 'older-zero-revision', 0,
                       'https://preexisting-zero-tag.example.invalid'),
                      r.rows_without_check(svc))

    def test_recovery_source_has_no_database_or_customer_mutation(self):
        source = inspect.getsource(r)
        for forbidden in ('psycopg', 'DATABASE_URL', 'schema_migrations',
                          'RICHON_MONTHLY_ENABLED=true',
                          'RICHON_MANUAL_ENABLED=true'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
