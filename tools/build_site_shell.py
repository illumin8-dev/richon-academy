"""Render the approved Richon public-site chrome into private account pages.

The current public landing/application files are intentionally untouched in this PR.
The shared fragments are copied only to the portal image and used by the fallback
OAuth pages + mypage. No deployment, credentials, network or data migration.
"""
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'frontend/shared'
STATIC = ROOT / 'backend/portal_static'


def wrapped(name: str, value: str) -> str:
    return '<!-- richon:shared-' + name + ' -->\n' + value.strip() + '\n<!-- /richon:shared-' + name + ' -->'


def outputs():
    header = (SOURCE / 'header.html').read_text()
    footer = (SOURCE / 'footer.html').read_text()
    result = {}
    for name in ('site.css', 'site.js', 'login.js', 'account.css', 'account.js'):
        result[STATIC / name] = (SOURCE / name).read_bytes()
    result[STATIC / 'site-header.html'] = header.encode()
    result[STATIC / 'site-footer.html'] = footer.encode()
    mypage = (SOURCE / 'mypage.html').read_text()
    mypage = mypage.replace('{{SITE_HEADER}}', wrapped('header', header))
    mypage = mypage.replace('{{SITE_FOOTER}}', wrapped('footer', footer))
    result[STATIC / 'mypage.html'] = mypage.encode()
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
        print('PASS: account surfaces use one shared header/footer and shared assets')
    else:
        for path, data in expected.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        print('Rendered shared account shell files: ' + str(len(expected)))


if __name__ == '__main__':
    main()
