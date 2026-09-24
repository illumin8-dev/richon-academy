"""Serve declared shared assets locally in existing no-network browser fixtures."""
from pathlib import Path
from urllib.parse import urlsplit

STATIC=Path(__file__).resolve().parents[1]/'portal_static'
FONT_CSS='https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css'
NAMES={'site.css','site.js','login.js','account.css','account.js'}


def shared_asset(route, origin):
    req=route.request;url=urlsplit(req.url)
    if req.method!='GET': return False
    if req.url==FONT_CSS:
        # Do not fetch external fonts or send test credentials to any provider.
        route.fulfill(status=200,content_type='text/css',body='/* offline typography fixture */')
        return True
    if url.scheme+'://'+url.netloc==origin and url.path.startswith('/portal/assets/') and url.path.rsplit('/',1)[1] in NAMES:
        name=url.path.rsplit('/',1)[1]
        route.fulfill(status=200,content_type='text/css' if name.endswith('.css') else 'text/javascript',body=(STATIC/name).read_bytes())
        return True
    return False
