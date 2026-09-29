"""UI family contract: shared auth/operations foundations without forcing one layout everywhere."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SHARED=ROOT/'frontend'/'shared'
STATIC=ROOT/'backend'/'portal_static'

def test_shared_auth_and_ops_assets_are_exact_copies():
    for name in ('auth.css','ops.css','site.css'):
        assert (SHARED/name).read_bytes()==(STATIC/name).read_bytes()

def test_operations_pages_share_brand_foundation_but_keep_page_css():
    pages={
        'admin.html':'/portal/assets/portal.css',
        'enrollments.html':'/portal/monthly-assets/enrollments.css',
        'manual.html':'/portal/manual-assets/manual.css',
    }
    for name,own in pages.items():
        text=(STATIC/name).read_text()
        assert '<link rel="stylesheet" href="/portal/assets/ops.css">' in text
        assert own in text
    ops=(STATIC/'ops.css').read_text()
    assert '--ops-orange:#f47920' in ops
    assert '--ops-font:' in ops
    for name in ('portal.css','enrollments.css','manual.css'):
        css=(STATIC/name).read_text()
        assert not css.startswith(':root{')
        assert '#ef7825' not in css

def test_standalone_auth_has_no_legacy_inline_theme():
    css=(SHARED/'auth.css').read_text()
    assert 'var(--site-orange)' in css
    assert '#fff7ed' not in css
    assert '#c44916' not in css


def test_course_admin_uses_shared_login_modal_gate():
    html=(STATIC/'courses.html').read_text()
    js=(STATIC/'courses.js').read_text()
    assert '/portal/assets/site.css' in html
    assert '/portal/assets/login.js' in html
    assert 'id="gate-login"' in html and 'data-richon-login' in html
    assert 'return_to=%2Fportal%2Fcourses' in html
    assert "e.status===401" in js and "$('gate-login').click()" in js

def test_auth_locked_fields_are_visual_not_explanatory():
    css=(SHARED/'auth.css').read_text()
    assert 'input[data-provider-locked=true]' in css
    assert '.provider-lock-badge' in css
    assert '.auth-main-signup' in css and '.auth-main-login' in css
