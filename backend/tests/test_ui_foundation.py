"""UI family contract: shared auth/operations foundations without forcing one layout everywhere."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SHARED=ROOT/'frontend'/'shared'
STATIC=ROOT/'backend'/'portal_static'

def test_shared_auth_and_ops_assets_are_exact_copies():
    for name in ('auth.css','ops.css','ops.js','site.css'):
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
    manual=(STATIC/'manual.css').read_text()
    for obsolete in ('header{','header>div{','.brand{','.brand span{','.side-note{','.footnote{','#identity{'):
        assert obsolete not in manual

def test_standalone_auth_has_no_legacy_inline_theme():
    css=(SHARED/'auth.css').read_text()
    assert 'var(--site-orange)' in css
    assert '#fff7ed' not in css
    assert '#c44916' not in css
