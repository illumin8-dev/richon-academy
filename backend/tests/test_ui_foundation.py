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
    enrollments=(STATIC/'enrollments.css').read_text()
    for obsolete in ('header{','header>div{','.brand{','.brand:before{','.aside-note{','.footnote{'):
        assert obsolete not in enrollments
    for shared_owned in (
        '.layout{display:grid;', '.eyebrow{font-size:11px;', 'h1{font-size:30px;',
        '.panel{background:#fff;', '.skip{position:absolute;', '.skip:focus{top:8px}',
    ):
        assert shared_owned not in enrollments
    assert 'h2{font-weight:700}' in enrollments
    assert '.filters{padding:20px}' in enrollments
    assert '.stats{margin:16px 0}' in enrollments
    assert '.pager{padding:15px 20px}' in enrollments
    for shared_owned in (
        '.eyebrow{font-size:10px;', 'h1{font-size:30px;', 'h2{font-size:19px;',
        '.panel{background:#fff;', '.filters{display:flex;align-items:end;',
        '.table-wrap{overflow-x:auto;max-width:100%}', '.skip{position:absolute;',
    ):
        assert shared_owned not in manual
    assert '.layout{min-height:calc(100vh - 78px)}' in manual
    assert '.pager{padding:16px 20px;font-size:12px}' in manual

def test_standalone_auth_has_no_legacy_inline_theme():
    css=(SHARED/'auth.css').read_text()
    assert 'var(--site-orange)' in css
    assert '#fff7ed' not in css
    assert '#c44916' not in css
