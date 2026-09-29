"""Safe OAuth callback stage diagnostics; synthetic logs only."""
import unittest
from unittest.mock import patch

import login_request_diagnostics as diag


class LoginRequestDiagnosticTests(unittest.TestCase):
    def test_only_allowlisted_stage_provider_pairs_are_counted(self):
        rows=[
            {'textPayload':'WARNING oauth_callback_failed stage=exchange_provider provider=kakao'},
            {'textPayload':'oauth_callback_failed stage=stage_signup provider=naver'},
            {'textPayload':'oauth_callback_failed stage=PRIVATE provider=kakao'},
            {'textPayload':'oauth_callback_failed stage=exchange_provider provider=PRIVATE'},
            {'textPayload':'PRIVATE SECRET TOKEN'},
        ]
        with patch.object(diag.c,'command',return_value=__import__('json').dumps(rows)):
            counts=diag.callback_stage_counts('richon-portal-handoff-1')
        self.assertEqual(counts[('exchange_provider','kakao')],1)
        self.assertEqual(counts[('stage_signup','naver')],1)
        self.assertEqual(sum(counts.values()),2)

    def test_raw_payload_is_never_returned(self):
        rows=[{'textPayload':'oauth_callback_failed stage=member_lookup provider=kakao PRIVATE=SECRET'}]
        with patch.object(diag.c,'command',return_value=__import__('json').dumps(rows)):
            counts=diag.callback_stage_counts('richon-portal-handoff-1')
        self.assertEqual(dict(counts),{('member_lookup','kakao'):1})
        self.assertNotIn('PRIVATE',repr(counts))
        self.assertNotIn('SECRET',repr(counts))


if __name__=='__main__':
    unittest.main()
