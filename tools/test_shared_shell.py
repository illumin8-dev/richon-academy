from pathlib import Path
import unittest
import build_site_shell as build
import shared_chrome as chrome

ROOT = build.ROOT
class SharedShellTests(unittest.TestCase):
    def test_generated_outputs_are_exact_and_idempotent(self):
        expected = build.outputs()
        self.assertEqual(expected, build.outputs())
        for path, data in expected.items():
            self.assertEqual(path.read_bytes(), data, str(path))

    def test_mypage_and_fallback_login_share_one_chrome_source(self):
        header = chrome.render_header('portal')
        footer = chrome.footer()
        page = (build.STATIC / 'mypage.html').read_text()
        self.assertEqual(page.count(header), 1)
        self.assertEqual(page.count(footer), 1)
        self.assertEqual(page.count('id="siteNav"'), 1)
        self.assertIn('data-richon-login hidden', page)

    def test_single_header_template_renders_all_variants(self):
        template=(build.SOURCE/'site-header.html').read_text()
        self.assertEqual(template.count('class="site-logo"'),1)
        self.assertIn('{{SITE_MENU}}',template)
        self.assertIn('{{SITE_ACTIONS}}',template)
        landing=chrome.render_header('landing')
        portal=chrome.render_header('portal')
        admin=chrome.render_header('admin')
        document=chrome.render_header('document')
        for rendered in (landing,portal,admin,document):
            self.assertIn('class="site-logo"',rendered)
            self.assertIn('RICH',rendered)
            self.assertIn('ON',rendered)
            self.assertIn('ESTATE STUDY',rendered)
            self.assertNotIn('{{SITE_',rendered)
        for label in ('후기','정규 프로그램','강사/멘토'):
            self.assertIn(label,landing)
            self.assertNotIn(label,portal)
            self.assertNotIn(label,admin)
        self.assertIn('오픈카톡방',portal)
        self.assertIn('강의 신청',portal)
        self.assertIn('운영 홈',admin)
        self.assertIn('← 홈으로',document)
        for legacy in ('header.html','portal-header.html','admin-header.html','admin-footer.html'):
            self.assertFalse((build.SOURCE/legacy).exists(),legacy)

    def test_public_source_pages_are_generated_from_shared_chrome(self):
        variants={
            'index.html':'landing',
            'apply.html':'portal',
            'signup-guide.html':'portal',
            'privacy.html':'document',
            'terms.html':'document',
        }
        footer=chrome.footer()
        for name,variant in variants.items():
            page=(ROOT/name).read_text()
            with self.subTest(name=name):
                self.assertIn(chrome.wrapped('header',chrome.render_header(variant)),page)
                self.assertIn(chrome.wrapped('footer',footer),page)

    def test_private_shared_assets_are_exact_copies(self):
        for name in ('site.css', 'site.js', 'login.js', 'signup.js', 'handoff.js', 'account.css', 'account.js'):
            self.assertEqual((build.SOURCE / name).read_bytes(), (build.STATIC / name).read_bytes())
        self.assertEqual((build.SOURCE / 'admin.css').read_bytes(), (build.STATIC / 'portal.css').read_bytes())
        site=(build.SOURCE/'site.css').read_text()
        self.assertTrue(site.startswith("@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');"))
        self.assertIn('--ops-font:var(--site-font)',(build.SOURCE/'ops.css').read_text())
        admin=(build.SOURCE/'admin.css').read_text()
        for obsolete in ('.topbar{','.brand-mark{','.top-actions{'):
            self.assertNotIn(obsolete,admin)
        self.assertNotIn('pretendard@v1.3.9',(build.SOURCE/'mypage.html').read_text())
        css = (build.SOURCE / 'account.css').read_text()
        self.assertIn('.account-withdrawal{font-size:12px', css)
        self.assertIn('color:#8a857d', css)
        self.assertNotIn('opacity:0', css)
        login = (build.SOURCE / 'login.js').read_text()
        self.assertIn('로그인을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.', login)
        self.assertIn("node('button','다시 시도'", login)
        self.assertNotIn('테스트 접근 인증', login)
        self.assertNotIn('접근 인증 후 로그인 화면 열기', login)


    def test_admin_shell_owns_outer_spacing(self):
        css=(build.SOURCE/'admin.css').read_text()
        for rule in ('body{padding-top:74px}', '.sidebar{border:0}', '.main{padding:0;max-width:none}', '.sidebar{top:98px}'):
            self.assertIn(rule,css)
        for name in ('admin.html','courses.html','enrollments.html','manual.html'):
            page=(build.STATIC/name).read_text()
            with self.subTest(name=name):
                self.assertIn('/portal/assets/portal.css',page)
        # Monthly/manual still contain legacy generic shell selectors, so the
        # canonical admin shell must load after them and win the cascade.
        for name,asset in (
            ('enrollments.html','/portal/monthly-assets/enrollments.css'),
            ('manual.html','/portal/manual-assets/manual.css'),
        ):
            page=(build.STATIC/name).read_text()
            self.assertGreater(page.find('/portal/assets/portal.css'),page.find(asset))
        # Course CSS is already scoped to course-specific controls and may load
        # after the shared shell.
        courses=(build.STATIC/'courses.html').read_text()
        self.assertGreater(courses.find('/portal/course-assets/courses.css'),courses.find('/portal/assets/portal.css'))

    def test_admin_pages_render_one_shared_shell(self):
        header=chrome.render_header('admin')
        footer=chrome.footer()
        sidebar=(build.SOURCE/'admin-sidebar.html').read_text()
        self.assertIn('class="site-nav admin-site-nav"',header)
        self.assertIn('class="site-logo"',header)
        self.assertNotIn('brand-mark',header)
        self.assertNotIn('class="topbar"',header)
        for name in ('admin.html','courses.html','enrollments.html','manual.html'):
            page=(build.STATIC/name).read_text()
            with self.subTest(name=name):
                self.assertEqual(page.count(header),1)
                self.assertEqual(page.count(footer),1)
                self.assertIn('/portal/assets/site.css',page)
                self.assertIn('/portal/assets/site.js',page)
                self.assertEqual(page.count('data-admin-tab-link="orders"'),1)
                self.assertEqual(page.count('data-admin-tab-link="members"'),1)
                self.assertNotIn('side-bottom',page)
                self.assertNotIn('class="ops-footer"',page)
                self.assertNotIn('brand-mark',page)
                self.assertGreater(page.find('class="site-footer"'),page.find('</main></div>'))
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
