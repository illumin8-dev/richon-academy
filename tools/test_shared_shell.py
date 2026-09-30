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
    'index.html': 'de9136fa71db2a672440ef3e59c47db26a73c6ef',
    'apply.html': '88a3095606a7afb74ec29dda40a1042c95ded1c7',
    'privacy.html': '903296249695223811375573c0a734d59fbdf70e',
    'terms.html': 'fac6ef6c734764797124710343fc02d405471077',
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
        header = (build.SOURCE / 'portal-header.html').read_text().strip()
        footer = (build.SOURCE / 'footer.html').read_text().strip()
        page = (build.STATIC / 'mypage.html').read_text()
        self.assertEqual(page.count(header), 1)
        self.assertEqual(page.count(footer), 1)
        self.assertEqual(page.count('id="siteNav"'), 1)
        self.assertIn('data-richon-login hidden', page)

    def test_public_and_portal_headers_keep_their_approved_boundaries(self):
        public = (ROOT / 'index.html').read_text()
        public_header = (build.SOURCE / 'header.html').read_text()
        portal_header = (build.SOURCE / 'portal-header.html').read_text()
        for label in ('RICH', 'ON', 'ESTATE STUDY', '오픈카톡방', '강의 신청'):
            self.assertIn(label, public)
            self.assertIn(label, public_header)
            self.assertIn(label, portal_header)
        for landing_label in ('후기', '정규 프로그램', '강사/멘토'):
            self.assertIn(landing_label, public)
            self.assertIn(landing_label, public_header)
            self.assertNotIn(landing_label, portal_header)
        for functional_forbidden in ('id="navMenu"', 'site-burger'):
            self.assertNotIn(functional_forbidden, portal_header)
        footer = (build.SOURCE / 'footer.html').read_text()
        for value in ('장순호', '175-01-03647', '032-236-8944', '개인정보처리방침', '이용약관'):
            self.assertIn(value, public)
            self.assertIn(value, footer)
        self.assertNotIn('회원가입 안내', footer)


    def test_public_pages_match_imported_upstream_authority(self):
        for name, expected in APPROVED.items():
            self.assertEqual(blob((ROOT / name).read_bytes()), expected, name)

    def test_private_shared_assets_are_exact_copies(self):
        for name in ('site.css', 'site.js', 'login.js', 'signup.js', 'handoff.js', 'account.css', 'account.js'):
            self.assertEqual((build.SOURCE / name).read_bytes(), (build.STATIC / name).read_bytes())
        css = (build.SOURCE / 'account.css').read_text()
        self.assertIn('.account-withdrawal{font-size:12px', css)
        self.assertIn('color:#8a857d', css)
        self.assertNotIn('opacity:0', css)
        login = (build.SOURCE / 'login.js').read_text()
        self.assertIn('로그인을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.', login)
        self.assertIn("node('button','다시 시도'", login)
        self.assertNotIn('테스트 접근 인증', login)
        self.assertNotIn('접근 인증 후 로그인 화면 열기', login)


    def test_admin_pages_render_one_shared_shell(self):
        header=(build.SOURCE/'admin-header.html').read_text().strip()
        footer=(build.SOURCE/'admin-footer.html').read_text().strip()
        sidebar=(build.SOURCE/'admin-sidebar.html').read_text()
        for name in ('admin.html','courses.html','enrollments.html','manual.html'):
            page=(build.STATIC/name).read_text()
            with self.subTest(name=name):
                self.assertEqual(page.count(header),1)
                self.assertEqual(page.count(footer),1)
                self.assertEqual(page.count('data-admin-tab-link="orders"'),1)
                self.assertEqual(page.count('data-admin-tab-link="members"'),1)
                self.assertNotIn('side-bottom',page)
        self.assertIn('신청·주문',sidebar)
        self.assertIn('회원 관리',sidebar)

    def test_admin_member_list_hides_internal_uuid_and_tmi(self):
        js=(build.STATIC/'portal.js').read_text()
        admin=(build.STATIC/'admin.html').read_text()
        self.assertNotIn("element('div',row.member_id,'secondary')",js)
        self.assertNotIn('회원번호 검색',js)
        self.assertNotIn('조회 버전',admin)
        self.assertNotIn('회원 수와 주문 수는 별도 집계',admin)
        self.assertNotIn('아직 실제 결제·수강 관리와 연결되지 않았습니다',admin)


if __name__ == '__main__':
    unittest.main()
