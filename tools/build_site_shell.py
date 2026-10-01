"""Render the approved Richon public-site chrome into private account pages.

The current public landing/application files are intentionally untouched in this PR.
The shared fragments are copied only to the portal image and used by the fallback
OAuth pages + mypage. No deployment, credentials, network or data migration.
"""
from pathlib import Path
import argparse
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'frontend/shared'
STATIC = ROOT / 'backend/portal_static'


def wrapped(name: str, value: str) -> str:
    return '<!-- richon:shared-' + name + ' -->\n' + value.strip() + '\n<!-- /richon:shared-' + name + ' -->'


def replace_wrapped(page: str, name: str, value: str) -> str:
    start='<!-- richon:shared-' + name + ' -->'
    end='<!-- /richon:shared-' + name + ' -->'
    pattern=re.escape(start)+r'.*?'+re.escape(end)
    replacement=wrapped(name,value)
    rendered,count=re.subn(pattern,replacement,page,count=1,flags=re.S)
    if count!=1:
        raise ValueError('missing_shared_marker_'+name)
    return rendered


def render_admin_sidebar(raw: str, active: str | None) -> str:
    for key in ('courses','enrollments','manual'):
        token='{{ACTIVE_'+key.upper()+'}}'
        raw=raw.replace(token,'aria-current="page"' if active==key else '')
    if '{{ACTIVE_' in raw:
        raise ValueError('unknown_admin_sidebar_token')
    return raw


def outputs():
    header = (SOURCE / 'portal-header.html').read_text()
    footer = (SOURCE / 'footer.html').read_text()
    result = {}
    for name in ('site.css', 'site.js', 'login.js', 'signup.js', 'handoff.js', 'auth.css', 'ops.css', 'account.css', 'account.js'):
        result[STATIC / name] = (SOURCE / name).read_bytes()
    # Keep the deployed /portal/assets/portal.css URL stable while making
    # frontend/shared/admin.css the single editable source for the admin shell.
    result[STATIC / 'portal.css'] = (SOURCE / 'admin.css').read_bytes()
    result[STATIC / 'site-header.html'] = header.encode()
    result[STATIC / 'site-footer.html'] = footer.encode()
    mypage = (SOURCE / 'mypage.html').read_text()
    mypage = mypage.replace('{{SITE_HEADER}}', wrapped('header', header))
    mypage = mypage.replace('{{SITE_FOOTER}}', wrapped('footer', footer))
    result[STATIC / 'mypage.html'] = mypage.encode()

    admin_header=(SOURCE/'admin-header.html').read_text()
    admin_sidebar=(SOURCE/'admin-sidebar.html').read_text()
    admin_footer=footer
    for filename,active in {
        'admin.html':None,
        'courses.html':'courses',
        'enrollments.html':'enrollments',
        'manual.html':'manual',
    }.items():
        page=(STATIC/filename).read_text()
        page=replace_wrapped(page,'admin-header',admin_header)
        page=replace_wrapped(page,'admin-sidebar',render_admin_sidebar(admin_sidebar,active))
        page=replace_wrapped(page,'admin-footer',admin_footer)
        result[STATIC/filename]=page.encode()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    expected = outputs()
    differences = [str(path.relative_to(ROOT)) for path, data in expected.items()
                   if not path.exists() or path.read_bytes() != data]
    if args.check:
        if differences:
            raise SystemExit('Shared account shell drift: ' + ', '.join(differences))
        print('PASS: account and admin surfaces use shared shell sources and shared assets')
    else:
        for path, data in expected.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        print('Rendered shared account/admin shell files: ' + str(len(expected)))


if __name__ == '__main__':
    main()
