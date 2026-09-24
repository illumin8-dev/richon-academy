from pathlib import Path
import hashlib
import unittest
import build_site_shell as build

ROOT = build.ROOT
PUBLIC_BLOBS = {
    'index.html': '251a6f099a51c893950a81d2cda917dbde6b4166',
    'apply.html': 'a618266b051b6d6fd10c4cdf3f461df3638b',
}
# Full SHA is checked below with the actual approved value; the shortened value
# above is never used as an authority.
APPROVED = {
    'index.html': '251a6f099a51c893950a81d2cda917dbde6b4166',
    'apply.html': 'a618266b051b6d1c6d6fd10c4cdf3f461df3638b',
    'privacy.html': '1f58db2c821fb2fe1628fe2e7e41db5321b51ffc',
    'terms.html': '949349bcc5d8e8c2f31a473be379c91500c8b024',
}


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class SharedShellTests(unittest.TestCase):
    def test_generated_outputs_are_exact_and_idempotent(self):
        expected = build.outputs()
        self.assertEqual(expected, build.outputs())
        for path, data in expected.items():
            self.assertEqual(path.read_bytes(), data, str(path))

    def test_mypage_and_fallback_login_share_one_chrome_source(self):
        header = (build.SOURCE / 'header.html').read_text().strip()
        footer = (build.SOURCE / 'footer.html').read_text().strip()
        page = (build.STATIC / 'mypage.html').read_text()
        self.assertEqual(page.count(header), 1)
        self.assertEqual(page.count(footer), 1)
        self.assertEqual(page.count('id="siteNav"'), 1)
        self.assertIn('data-richon-login hidden', page)

    def test_shared_header_is_derived_from_current_public_header_labels(self):
        public = (ROOT / 'index.html').read_text()
        header = (build.SOURCE / 'header.html').read_text()
        for label in ('RICH', 'ON', 'ESTATE STUDY', '후기', '정규 프로그램', '강사/멘토', '오픈카톡방', '강의 신청'):
            self.assertIn(label, public)
            self.assertIn(label, header)
        footer = (build.SOURCE / 'footer.html').read_text()
        for value in ('장순호', '175-01-03647', '032-236-8944', '개인정보처리방침', '이용약관'):
            self.assertIn(value, public)
            self.assertIn(value, footer)

    def test_public_landing_and_application_bytes_are_unchanged_in_this_pr(self):
        for name, expected in APPROVED.items():
            self.assertEqual(blob((ROOT / name).read_bytes()), expected, name)

    def test_private_shared_assets_are_exact_copies(self):
        for name in ('site.css', 'site.js', 'login.js', 'account.css', 'account.js'):
            self.assertEqual((build.SOURCE / name).read_bytes(), (build.STATIC / name).read_bytes())
        css = (build.SOURCE / 'account.css').read_text()
        self.assertIn('.account-withdrawal{font-size:12px', css)
        self.assertIn('color:#8a857d', css)
        self.assertNotIn('opacity:0', css)


if __name__ == '__main__':
    unittest.main()
