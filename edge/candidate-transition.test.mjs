// Isolated transport tests. No external requests, real provider, or credentials.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {handle, allowed, safeLocation} from './worker.mjs';
const SITE='https://richonacademy.com';
const SERVICE='https://richon-portal-amjmgyepbq-as.a.run.app';
const CANDIDATE='https://portal-candidate---richon-portal-amjmgyepbq-as.a.run.app';
const env={PORTAL_ENABLED:'true',PORTAL_UPSTREAM:CANDIDATE,RICHON_EDGE_SECRET:'s'.repeat(43)};
const forbiddenFetch=()=>assert.fail('unexpected network');

test('exact candidate and rollback target both work without redirecting browser to run.app',async()=>{
  for(const upstream of [CANDIDATE,SERVICE]) {
    let seen;
    const result=await handle(new Request(SITE+'/auth/login'),{...env,PORTAL_UPSTREAM:upstream},async(url,init)=>{
      seen={url,init};return new Response('<form></form>',{headers:{'Content-Type':'text/html'}});
    });
    assert.equal(result.status,200);assert.equal(seen.url,upstream+'/auth/login');
    assert.equal(result.headers.get('Location'),null);
    assert.equal(seen.init.headers.get('X-Richon-Edge-Key'),env.RICHON_EDGE_SECRET);
    assert.equal(seen.init.cache,'no-store');assert.equal(seen.init.redirect,'manual');
    assert.equal(result.headers.get('Referrer-Policy'),'same-origin');
  }
});

test('other tags, foreign hosts, credentials, paths, queries and ports are denied',async()=>{
  for(const target of [
    CANDIDATE.replace('portal-candidate---','other---'),CANDIDATE+'.evil.invalid',
    CANDIDATE.replace('amjmgyepbq','foreign'),CANDIDATE.replace('https:','http:'),
    CANDIDATE.replace('https://','https://name:password@'),CANDIDATE+'/auth/login',
    CANDIDATE+'?x=1',CANDIDATE+'#x',CANDIDATE+':444',
  ]) {
    const result=await handle(new Request(SITE+'/auth/login'),{...env,PORTAL_UPSTREAM:target},forbiddenFetch);
    assert.equal(result.status,503,target);
  }
});

test('Naver image is an exact GET-only path and still uses the origin gate',async()=>{
  const path='/auth/assets/naver-login.png';assert.equal(allowed(path,'GET'),true);
  assert.equal(allowed(path,'POST'),false);assert.equal(allowed('/auth/assets/other.png','GET'),false);
  let seen;
  const result=await handle(new Request(SITE+path),env,async(url,init)=>{
    seen={url,init};return new Response(new Uint8Array([137,80,78,71]),{headers:{'Content-Type':'image/png'}});
  });
  assert.equal(result.status,200);assert.equal(seen.url,CANDIDATE+path);
  assert.equal(seen.init.headers.get('X-Richon-Edge-Key'),env.RICHON_EDGE_SECRET);
  assert.equal(result.headers.get('Referrer-Policy'),'no-referrer');
  assert.equal(result.headers.get('Cache-Control'),'no-store');
  const denied=await handle(new Request(SITE+path,{method:'POST',body:'x'}),env,forbiddenFetch);
  assert.equal(denied.status,404);
});

test('candidate route preserves invalid Origin rejection and strips Access cookies',async()=>{
  let sent;
  const result=await handle(new Request(SITE+'/auth/start',{method:'POST',body:'csrf=invalid&provider=naver',headers:{
    Origin:'null',Cookie:'CF_Authorization=synthetic; __Host-richon-oauth=synthetic',
    'X-Richon-Edge-Key':'spoof',Authorization:'Bearer synthetic',
  }}),env,async(url,init)=>{
    sent=init;return new Response('{"detail":"invalid_login_flow"}',{status:403,headers:{'Content-Type':'application/json'}});
  });
  assert.equal(result.status,403);assert.equal(sent.headers.get('Origin'),'null');
  assert.equal(sent.headers.get('Cookie'),'__Host-richon-oauth=synthetic');
  assert.equal(sent.headers.get('Authorization'),null);
  assert.equal(sent.headers.get('X-Richon-Edge-Key'),env.RICHON_EDGE_SECRET);
  assert.equal(result.headers.get('Set-Cookie'),null);
});

test('both provider redirects and previous-page returns remain unchanged',async()=>{
  for(const endpoint of ['https://kauth.kakao.com/oauth/authorize?state=synthetic','https://nid.naver.com/oauth2.0/authorize?state=synthetic']) {
    let count=0;
    const result=await handle(new Request(SITE+'/auth/start',{method:'POST',body:'synthetic'}),env,async()=>{
      count++;return new Response(null,{status:303,headers:{Location:endpoint}});
    });
    assert.equal(count,1);assert.equal(result.headers.get('Location'),endpoint);
  }
  for(const provider of ['kakao','naver']) {
    assert.equal(safeLocation('/apply.html',`/auth/${provider}/callback`),SITE+'/apply.html');
    assert.throws(()=>safeLocation(CANDIDATE+'/auth/login',`/auth/${provider}/callback`));
  }
});

test('response cookies stay host-only and separate on candidate responses',async()=>{
  const cookies=['__Host-richon-signup=synthetic; Secure; HttpOnly; SameSite=lax; Path=/',
    '__Host-richon-oauth=; Max-Age=0; Secure; HttpOnly; SameSite=lax; Path=/'];
  const headers=new Headers({Location:'/auth/signup'});for(const value of cookies)headers.append('Set-Cookie',value);
  const result=await handle(new Request(SITE+'/auth/naver/callback?code=synthetic&state=synthetic'),env,async()=>new Response(null,{status:303,headers}));
  assert.deepEqual(result.headers.getSetCookie(),cookies);
  assert.equal(result.headers.get('Location'),SITE+'/auth/signup');
  assert.equal(result.headers.get('Referrer-Policy'),'no-referrer');
});

test('missing server key and disabled proxy still perform no requests',async()=>{
  for(const config of [{...env,RICHON_EDGE_SECRET:''},{...env,PORTAL_ENABLED:'false'}]) {
    const result=await handle(new Request(SITE+'/auth/login'),config,forbiddenFetch);
    assert.equal(result.status,503);
  }
});

test('deployment config retains existing exposure settings and selects exact candidate',()=>{
  const config=readFileSync(new URL('./wrangler.toml',import.meta.url),'utf8');
  assert.match(config,/^workers_dev = false$/m);assert.match(config,/^preview_urls = false$/m);
  assert.match(config,/^PORTAL_ENABLED = "true"$/m);
  assert.ok(config.includes(`PORTAL_UPSTREAM = "${CANDIDATE}"`));
  assert.ok(config.includes(`Rollback: restore PORTAL_UPSTREAM to ${SERVICE}`));
  assert.doesNotMatch(config,/^routes?\s*=/m);
  assert.doesNotMatch(config,/^RICHON_EDGE_SECRET\s*=/m);
  assert.match(config,/\[observability\]\nenabled = false/);
});
