/** A-plan edge proxy. Disabled until a separate portal origin is approved. */
const ORIGIN = 'https://richonacademy.com';
const LIMIT = 65536;
const PUBLIC_RETURNS = new Set(['/', '/index.html', '/apply.html']);
const PORTAL_RETURNS = new Set(['/portal/mypage', '/portal/admin', '/portal/enrollments', '/portal/manual']);
const COMPLETIONS = new Set(['/auth/kakao/callback', '/auth/naver/callback', '/auth/signup']);
const COOKIES = new Set(['__Host-richon-session', '__Host-richon-oauth', '__Host-richon-signup']);
const AUTH = new Map([
  ['/auth/login', ['GET']], ['/auth/start', ['POST']], ['/auth/signup', ['GET', 'POST']],
  ['/auth/kakao/callback', ['GET']], ['/auth/naver/callback', ['GET']],
  ['/auth/assets/kakao-login.png', ['GET']],
  ['/auth/assets/naver-login.png', ['GET']],
  ['/auth/me', ['GET']], ['/auth/csrf', ['GET']], ['/auth/logout', ['POST']], ['/auth/logout-all', ['POST']],
]);
export function allowed(path, method) {
  if (!/^\/(auth|portal)\/[A-Za-z0-9_./-]+$/.test(path) || path.split('/').slice(1).some(x => !x || x === '.' || x === '..')) return false;
  return path.startsWith('/auth/') ? (AUTH.get(path) || []).includes(method) : ['GET', 'POST'].includes(method);
}
function failure(status, detail) {
  return new Response(JSON.stringify({detail}), {status, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}});
}
export function safeLocation(value, path) {
  const url = new URL(value, ORIGIN);
  if (url.username || url.password || url.hash) throw new Error('unsafe_redirect');
  if (url.origin === ORIGIN && allowed(url.pathname, 'GET')) return url.href;
  if (url.origin === ORIGIN && COMPLETIONS.has(path) && PUBLIC_RETURNS.has(url.pathname) && !url.search
    && [url.pathname, ORIGIN + url.pathname].includes(value)) return url.href;
  if (path === '/auth/start' && ((url.origin === 'https://kauth.kakao.com' && url.pathname === '/oauth/authorize')
    || (url.origin === 'https://nid.naver.com' && url.pathname === '/oauth2.0/authorize'))) return url.href;
  throw new Error('unsafe_redirect');
}
async function readBody(request) {
  if (!request.body) return undefined;
  const reader = request.body.getReader(), chunks = [];
  let total = 0;
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > LIMIT) { await reader.cancel(); throw new Error('oversize'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const body = new Uint8Array(total); let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  return body;
}
export function returnReferer(value) {
  // Navigation hint only, with query/fragment stripped before sending upstream.
  if (!value || value.length > 2048 || /[\x00-\x20\x7f\\]/.test(value)) return null;
  try {
    const url = new URL(value);
    if (url.origin === ORIGIN && !url.username && !url.password
      && (PUBLIC_RETURNS.has(url.pathname) || PORTAL_RETURNS.has(url.pathname))
      && value.split(/[?#]/, 1)[0] === ORIGIN + url.pathname) return ORIGIN + url.pathname;
  } catch { /* No raw input is logged. */ }
  return null;
}
export function responseReferrerPolicy(path, method, status, type) {
  return method === 'GET' && ['/auth/login', '/auth/signup'].includes(path)
    && status === 200 && type?.toLowerCase().split(';')[0].trim() === 'text/html'
    ? 'same-origin' : 'no-referrer';
}
export async function handle(request, env, fetcher = fetch) {
  const url = new URL(request.url);
  if (url.origin !== ORIGIN || !allowed(url.pathname, request.method) || url.pathname.includes('%') || url.pathname.includes('\\')) return failure(404, 'not_found');
  if (url.search.length > 8192) return failure(414, 'request_too_large');
  if (env.PORTAL_ENABLED !== 'true') return failure(503, 'portal_not_enabled');
  let upstream;
  try {
    upstream = new URL(env.PORTAL_UPSTREAM);
    if (upstream.protocol !== 'https:' || !/^richon-portal-[a-z0-9.-]+\.run\.app$/.test(upstream.hostname)
      || upstream.port || upstream.username || upstream.password || upstream.pathname !== '/' || upstream.search || upstream.hash
      || !/^[A-Za-z0-9_-]{43,128}$/.test(env.RICHON_EDGE_SECRET || '')) throw new Error('invalid_config');
  } catch { return failure(503, 'portal_not_configured'); }
  const length = request.headers.get('content-length');
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > LIMIT)) return failure(413, 'request_too_large');
  let body;
  try { body = await readBody(request); } catch { return failure(413, 'request_too_large'); }
  // Preserve the actual browser Origin. Never fabricate a same-origin CSRF proof.
  const headers = new Headers();
  for (const key of ['accept', 'content-type', 'origin', 'sec-fetch-site', 'x-csrf-token']) {
    const value = request.headers.get(key); if (value !== null) headers.set(key, value);
  }
  if (url.pathname === '/auth/login' && request.method === 'GET') {
    const previous = returnReferer(request.headers.get('referer'));
    if (previous) headers.set('Referer', previous);
  }
  const cookies = (request.headers.get('cookie') || '').split(';').map(x => x.trim()).filter(x => COOKIES.has(x.split('=',1)[0]));
  if (cookies.length) headers.set('Cookie', cookies.join('; '));
  headers.set('X-Richon-Edge-Key', env.RICHON_EDGE_SECRET);
  const destination = new URL(url.pathname + url.search, upstream.origin);
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 30000);
  try {
    const result = await fetcher(destination.href, {method: request.method, headers, body,
      redirect: 'manual', signal: controller.signal, cache: 'no-store'});
    const output = new Headers({'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer', 'X-Content-Type-Options':'nosniff', 'X-Frame-Options':'DENY'});
    for (const key of ['content-type', 'content-security-policy', 'retry-after']) {
      const value = result.headers.get(key); if (value) output.set(key, value);
    }
    output.set('Referrer-Policy', responseReferrerPolicy(url.pathname, request.method, result.status, result.headers.get('content-type')));
    if (result.status >= 300 && result.status < 400) {
      const location = result.headers.get('location');
      if (!location) throw new Error('missing_location');
      output.set('Location', safeLocation(location, url.pathname));
    }
    const setCookies = typeof result.headers.getSetCookie === 'function'
      ? result.headers.getSetCookie() : result.headers.getAll('Set-Cookie');
    for (const cookie of setCookies) {
      const parts = cookie.split(';').map(x => x.trim());
      const attrs = parts.slice(1).map(x => x.toLowerCase());
      if (!COOKIES.has(parts[0].split('=',1)[0]) || !attrs.includes('secure') || !attrs.includes('httponly')
        || !attrs.includes('path=/') || !attrs.includes('samesite=lax') || attrs.some(x => /^domain\s*=/.test(x))) throw new Error('invalid_cookie');
      output.append('Set-Cookie', cookie);
    }
    return new Response(result.body, {status: result.status, headers: output});
  } catch { return failure(502, 'portal_unavailable'); }
  finally { clearTimeout(timer); }
}
export default {fetch(request, env) { return handle(request, env); }};
