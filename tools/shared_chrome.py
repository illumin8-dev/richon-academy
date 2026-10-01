"""Canonical Richon site chrome renderer.

Only frontend/shared/site-header.html and frontend/shared/footer.html are editable
chrome sources. Page-specific variants supply menu/action slots without duplicating
the shared logo/header structure.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "shared"

HEADER_TEMPLATE = SOURCE / "site-header.html"
FOOTER = SOURCE / "footer.html"
PRETENDARD_STYLESHEET = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"
PRETENDARD_LINK = '<link rel="stylesheet" as="style" crossorigin href="' + PRETENDARD_STYLESHEET + '">'

PUBLIC_ACTIONS = """    <a class="site-btn site-btn-line site-chat" href="https://open.kakao.com/o/gPdQcklh" target="_blank" rel="noopener noreferrer">오픈카톡방</a>
    <a class="site-btn site-btn-o" href="/apply.html">강의 신청</a>
    <a class="site-account-link" id="site-account-login" href="/auth/login" data-richon-login hidden>로그인</a>
    <a class="site-account-link" id="site-account-me" href="/portal/mypage" hidden>마이페이지</a>
    <button class="site-account-link" id="logout" type="button" hidden>로그아웃</button>"""

LANDING_MENU = """  <div class="site-menu" id="navMenu">
    <a href="/#proof">후기</a>
    <a href="/#programs">정규 프로그램</a>
    <a href="/#instructor">강사/멘토</a>
  </div>"""

LANDING_ACTIONS = PUBLIC_ACTIONS + """
    <button class="site-burger" id="burger" type="button" aria-controls="navMenu" aria-label="메뉴" aria-expanded="false"><span></span><span></span><span></span></button>"""

ADMIN_ACTIONS = """    <a class="site-account-link" href="/portal/admin?tab=orders">운영 홈</a>
    <a class="site-account-link" href="/portal/mypage">마이페이지</a>
    <button class="site-account-link" id="logout" type="button" hidden>로그아웃</button>"""

DOCUMENT_ACTIONS = """    <a class="site-btn site-btn-line" href="/">← 홈으로</a>"""


def render_header(variant: str) -> str:
    values = {
        "landing": {
            "SITE_NAV_CLASS": "",
            "SITE_ARIA_LABEL": "리치온 아카데미 메뉴",
            "SITE_MENU": LANDING_MENU,
            "SITE_ACTIONS": LANDING_ACTIONS,
        },
        "portal": {
            "SITE_NAV_CLASS": "",
            "SITE_ARIA_LABEL": "리치온 아카데미 메뉴",
            "SITE_MENU": "",
            "SITE_ACTIONS": PUBLIC_ACTIONS,
        },
        "admin": {
            "SITE_NAV_CLASS": " admin-site-nav",
            "SITE_ARIA_LABEL": "리치온 아카데미 관리자 메뉴",
            "SITE_MENU": "",
            "SITE_ACTIONS": ADMIN_ACTIONS,
        },
        "document": {
            "SITE_NAV_CLASS": "",
            "SITE_ARIA_LABEL": "리치온 아카데미 문서 메뉴",
            "SITE_MENU": "",
            "SITE_ACTIONS": DOCUMENT_ACTIONS,
        },
    }
    if variant not in values:
        raise ValueError("unknown_site_header_variant_" + variant)
    rendered = HEADER_TEMPLATE.read_text()
    for key, value in values[variant].items():
        rendered = rendered.replace("{{" + key + "}}", value)
    if "{{SITE_" in rendered:
        raise ValueError("unresolved_site_header_token")
    return rendered.strip()


def footer() -> str:
    return FOOTER.read_text().strip()


def wrapped(name: str, value: str) -> str:
    return "<!-- richon:shared-" + name + " -->\n" + value.strip() + "\n<!-- /richon:shared-" + name + " -->"


def replace_wrapped(page: str, name: str, value: str) -> str:
    import re
    start = "<!-- richon:shared-" + name + " -->"
    end = "<!-- /richon:shared-" + name + " -->"
    pattern = re.escape(start) + r".*?" + re.escape(end)
    rendered, count = re.subn(pattern, wrapped(name, value), page, count=1, flags=re.S)
    if count != 1:
        raise ValueError("missing_shared_marker_" + name)
    return rendered


def font_link() -> str:
    """Return the exact font link used by the original public homepage."""
    return PRETENDARD_LINK


def ensure_font_link(page: str) -> str:
    """Keep one canonical Pretendard link in the page head without CSS @import."""
    import re
    page = re.sub(r'\s*<link[^>]+pretendard@v1\.3\.9[^>]*>\s*', '\n', page, flags=re.I)
    positions = [position for position in (
        page.find('<style'),
        page.find('<link rel="stylesheet" href="frontend/shared/site.css">'),
        page.find('<link rel="stylesheet" href="/frontend/shared/site.css">'),
        page.find('<link rel="stylesheet" href="/portal/assets/site.css">'),
        page.find('<link rel="stylesheet" href="/auth/assets/site.css">'),
        page.find('</head>'),
    ) if position >= 0]
    if not positions:
        raise ValueError("missing_head_font_anchor")
    at = min(positions)
    return page[:at] + font_link() + '\n' + page[at:]
