"""A-plan portal-only ASGI entry. Never mount private orders or database health.
Prepared for a separate Cloud Run service, NOT for exposing richon-backend-test.
"""
import hmac
import os
import re
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import auth_http
import oauth_http
import portal
import monthly_portal
import manual_portal

ORIGIN = 'https://richonacademy.com'
LIMIT = 65536
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
           'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY'}


def allowed(path, method):
    if not re.fullmatch(r'/(?:auth|portal)/[A-Za-z0-9_./-]+', path):
        return False
    if any(part in ('', '.', '..') for part in path.split('/')[1:]):
        return False
    auth_methods = {
        '/auth/login': {'GET'}, '/auth/start': {'POST'},
        '/auth/assets/kakao-login.png': {'GET'},
        '/auth/assets/naver-login.png': {'GET'},
        '/auth/signup': {'GET', 'POST'},
        '/auth/kakao/callback': {'GET'}, '/auth/naver/callback': {'GET'},
        '/auth/me': {'GET'}, '/auth/csrf': {'GET'},
        '/auth/logout': {'POST'}, '/auth/logout-all': {'POST'},
    }
    if path.startswith('/auth/'):
        return method in auth_methods.get(path, set())
    return method in {'GET', 'POST'}


class EdgeBoundary:
    """An origin gate, not a substitute for member/admin authorization."""
    def __init__(self, app, enabled=False, secret=''):
        self.app, self.enabled, self.secret = app, enabled, secret
        if enabled and not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', secret):
            raise ValueError('portal_edge_secret_required')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async def reject(status, detail):
            await JSONResponse({'detail': detail}, status_code=status, headers=HEADERS)(scope, receive, send)
        if not self.enabled:
            return await reject(503, 'portal_not_enabled')
        values = [v for k, v in scope['headers'] if k.lower() == b'x-richon-edge-key']
        if len(values) != 1 or not hmac.compare_digest(values[0], self.secret.encode('ascii')):
            return await reject(403, 'edge_required')
        if (b'%' in scope.get('raw_path', b'') or b'\\' in scope.get('raw_path', b'')
                or not allowed(scope['path'], scope['method'])):
            return await reject(404, 'not_found')
        lengths = [v for k, v in scope['headers'] if k.lower() == b'content-length']
        if len(lengths) > 1 or (lengths and (not lengths[0].isdigit() or int(lengths[0]) > LIMIT)):
            return await reject(413, 'request_too_large')
        if len(scope.get('query_string', b'')) > 8192:
            return await reject(414, 'request_too_large')
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > LIMIT:
                return await reject(413, 'request_too_large')
            if not message.get('more_body', False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
        scope = dict(scope)
        scope['headers'] = [(k,v) for k,v in scope['headers'] if k.lower() != b'x-richon-edge-key']
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                headers = [(k,v) for k,v in message['headers'] if k.lower() not in {b'cache-control', b'referrer-policy'}]
                form_page = (scope['method'] == 'GET' and scope['path'] in {'/auth/login', '/auth/signup', '/portal/mypage'}
                             and message['status'] == 200
                             and any(k.lower() == b'content-type' and v.lower().split(b';')[0] == b'text/html'
                                     for k,v in headers))
                policy = b'same-origin' if form_page else b'no-referrer'
                message = {**message, 'headers': headers + [(b'cache-control', b'no-store'), (b'referrer-policy', policy)]}
            await send(message)
        await self.app(scope, replay, secure_send)


def build_app():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, debug=False)
    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({'detail': 'invalid_request'}, status_code=422, headers=HEADERS)
    enabled = os.getenv('RICHON_EDGE_ENABLED', 'false') == 'true'
    if enabled:
        if not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', os.getenv('RICHON_EDGE_SECRET', '')):
            raise ValueError('portal_edge_secret_required')
        if os.getenv('RICHON_OAUTH_ORIGIN') != ORIGIN:
            raise ValueError('a_plan_origin_required')
        if not auth_http.install_if_enabled(app) or not oauth_http.install_if_enabled(app):
            raise ValueError('portal_login_required')
        if not portal.install_if_enabled(app):
            raise ValueError('portal_pages_required')
        monthly_portal.install_if_enabled(app)
        manual_portal.install_if_enabled(app)
    app.add_middleware(EdgeBoundary, enabled=enabled, secret=os.getenv('RICHON_EDGE_SECRET', ''))
    return app


app = build_app()
