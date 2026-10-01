"""Render the approved Richon public-site chrome into private account pages.

The current public landing/application files are intentionally untouched in this PR.
The shared fragments are copied only to the portal image and used by the fallback
OAuth pages + mypage. No deployment, credentials, network or data migration.
"""
from pathlib import Path
import argparse
import shared_chrome as chrome

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'frontend/shared'
STATIC = ROOT / 'backend/portal_static'


def render_admin_sidebar(raw: str, active: str | None) -> str:
    for key in ('courses','enrollments','manual'):
        token='{{ACTIVE_'+key.upper()+'}}'
        raw=raw.replace(token,'aria-current="page"' if active==key else '')
    if '{{ACTIVE_' in raw:
        raise ValueError('unknown_admin_sidebar_token')
    return raw


def outputs():
    header = chrome.render_header('portal')
    footer = chrome.footer()
    result = {}
    for name in ('site.css', 'site.js', 'login.js', 'signup.js', 'handoff.js', 'auth.css', 'ops.css', 'account.css', 'account.js'):
        result[STATIC / name] = (SOURCE / name).read_bytes()
    # Keep the deployed /portal/assets/portal.css URL stable while making
    # frontend/shared/admin.css the single editable source for the admin shell.
    result[STATIC / 'portal.css'] = (SOURCE / 'admin.css').read_bytes()
    result[STATIC / 'site-header.html'] = (header + '\n').encode()
    result[STATIC / 'site-footer.html'] = (footer + '\n').encode()
    mypage = (SOURCE / 'mypage.html').read_text()
    mypage = mypage.replace('{{SITE_HEADER}}', chrome.wrapped('header', header))
    mypage = mypage.replace('{{SITE_FOOTER}}', chrome.wrapped('footer', footer))
    result[STATIC / 'mypage.html'] = mypage.encode()

    admin_header=chrome.render_header('admin')
    admin_sidebar=(SOURCE/'admin-sidebar.html').read_text()
    admin_footer=footer
    for filename,active in {
        'admin.html':None,
        'courses.html':'courses',
        'enrollments.html':'enrollments',
        'manual.html':'manual',
    }.items():
        page=(STATIC/filename).read_text()
        page=chrome.replace_wrapped(page,'admin-header',admin_header)
        page=chrome.replace_wrapped(page,'admin-sidebar',render_admin_sidebar(admin_sidebar,active))
        page=chrome.replace_wrapped(page,'admin-footer',admin_footer)
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
