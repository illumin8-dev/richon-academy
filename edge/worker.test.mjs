import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker, {handle, allowed, safeLocation} from './worker.mjs';
const origin='https://richonacademy.com';
const env={PORTAL_ENABLED:'true',PORTAL_UPSTREAM:'https://richon-portal-synthetic.as.run.app',RICHON_EDGE_SECRET:'s'.repeat(43)};
const req=(path='/auth/login',init)=>new Request(origin+path,init);
const cookie='__Host-richon-session=test; HttpOnly; Path=/; SameSite=lax; Secure';

test('only login and portal paths / limited methods',()=>{
  for(const path of ['/health/db','/orders','/index.html','/apply.html','/auth/fake-login','/portal//manual','/portal/../orders','/portal/%2forder'])assert.equal(allowed(path,'GET'),false);
  assert.equal(allowed('/auth/start','GET'),false);assert.equal(allowed('/portal/manual','DELETE'),false);
  assert.equal(allowed('/portal/api/admin/manual/create','POST'),true);
});
test('disabled proxy performs no network request',async()=>{
  const r=await handle(req(),{...env,PORTAL_ENABLED:'false'},()=>assert.fail('unexpected network'));assert.equal(r.status,503);
});
test('reject missing secret or private-service upstream',async()=>{
  for(const config of [{...env,RICHON_EDGE_SECRET:''},{...env,PORTAL_UPSTREAM:'https://richon-backend-test-amjmgyepbq-as.a.run.app'},{...env,PORTAL_UPSTREAM:'http://richon-portal-synthetic.as.run.app'},{...env,PORTAL_UPSTREAM:'https://evil.invalid'},{...env,PORTAL_UPSTREAM:env.PORTAL_UPSTREAM+'/anything'}]){
    assert.equal((await handle(req(),config,()=>assert.fail('unexpected network'))).status,503);
  }
});
test('reject alternate host and private paths without network',async()=>{
  for(const request of [new Request('https://www.richonacademy.com/auth/login'),req('/orders'),req('/auth/%6cogin'),req('/portal/manual',{method:'DELETE'})]){
    assert.equal((await handle(request,env,()=>assert.fail('network'))).status,404);
  }
});
test('preserve browser origin, strip credential spoofing and unrelated cookies',async()=>{
  const r=await handle(req('/auth/start',{method:'POST',body:'provider=kakao',headers:{Origin:'https://evil.invalid',Authorization:'Bearer user-controlled','X-Richon-Edge-Key':'spoof','X-Forwarded-Host':'evil.invalid',Cookie:'__Host-richon-oauth=test; unrelated=private'}}),env,async(url,init)=>{
    assert.equal(url,env.PORTAL_UPSTREAM+'/auth/start');assert.equal(init.redirect,'manual');
    assert.equal(init.headers.get('origin'),'https://evil.invalid');assert.equal(init.headers.get('authorization'),null);
    assert.equal(init.headers.get('x-forwarded-host'),null);assert.equal(init.headers.get('x-richon-edge-key'),env.RICHON_EDGE_SECRET);
    assert.equal(init.headers.get('cookie'),'__Host-richon-oauth=test');return new Response('{}',{status:403});
  });
  assert.equal(r.status,403);assert.equal(r.headers.get('cache-control'),'no-store');
});
test('OAuth redirects are returned rather than fetched',async()=>{
  const location='https://kauth.kakao.com/oauth/authorize?state=synthetic';let calls=0;
  const r=await handle(req('/auth/start',{method:'POST',body:'x=y'}),env,async()=>{calls++;return new Response(null,{status:303,headers:{Location:location}});});
  assert.equal(calls,1);assert.equal(r.status,303);assert.equal(r.headers.get('location'),location);
  assert.equal(safeLocation('/portal/mypage','/auth/kakao/callback'),origin+'/portal/mypage');
  for(const bad of ['https://evil.invalid/','//evil.invalid/auth/login','https://user@richonacademy.com/auth/login','/orders','/auth/login#token'])assert.throws(()=>safeLocation(bad,'/auth/start'));
});
test('multiple host-only secure cookies are preserved independently',async()=>{
  const headers=new Headers();headers.append('Set-Cookie',cookie);headers.append('Set-Cookie','__Host-richon-oauth=; Max-Age=0; HttpOnly; Path=/; SameSite=lax; Secure');
  const r=await handle(req(),env,async()=>new Response('ok',{headers}));assert.equal(r.status,200);assert.equal(r.headers.getSetCookie().length,2);
});
test('cookie domain, unapproved cookie, and unsafe redirect rejected',async()=>{
  for(const headers of [{'Set-Cookie':cookie+'; Domain=richonacademy.com'},{'Set-Cookie':'other=value; Secure; HttpOnly; Path=/; SameSite=lax'},{Location:'https://evil.invalid'}]){
    const r=await handle(req(),env,async()=>new Response(null,{status:headers.Location?302:200,headers}));
    assert.equal(r.status,502);assert.equal(r.headers.get('set-cookie'),null);
  }
});
test('chunked / declared oversized request never reaches origin',async()=>{
  for(const request of [req('/auth/start',{method:'POST',body:'a'.repeat(65537)}),req('/auth/start',{method:'POST',headers:{'Content-Length':'70000'},body:'x'})]){
    assert.equal((await handle(request,env,()=>assert.fail('network'))).status,413);
  }
});
test('transport failure is safe and never echoes inputs',async()=>{
  const r=await handle(req('/auth/kakao/callback?code=PRIVATE'),env,()=>{throw new Error('PRIVATE');});assert.equal(r.status,502);assert.equal((await r.text()).includes('PRIVATE'),false);
});
test('Worker entry ignores execution context as transport',async()=>{
  const original=globalThis.fetch;let calls=0;globalThis.fetch=async()=>{calls++;return new Response('ok');};
  try{const r=await worker.fetch(req(),env,{waitUntil(){}});assert.equal(r.status,200);assert.equal(calls,1);}finally{globalThis.fetch=original;}
});

// Transport contract tests only: the Cloudflare CDN and OAuth providers are not
// emulated here. These assertions prevent reintroducing forced cache TTLs.
test('all auth and portal subrequests bypass cache rather than cache with TTL zero',async()=>{
  const cases=[['/auth/login','GET'],['/auth/signup','GET'],['/auth/kakao/callback','GET'],
    ['/auth/naver/callback','GET'],['/auth/assets/kakao-login.png','GET'],['/auth/me','GET'],
    ['/portal/mypage','GET'],['/auth/start','POST'],['/auth/signup','POST'],['/auth/logout','POST']];
  for(const [path,method] of cases){
    let observed;
    const r=await handle(req(path,{method,...(method==='POST'?{body:'csrf=synthetic'}:{})}),env,async(url,init)=>{
      observed=init;return new Response('{}',{headers:{'Content-Type':'application/json'}});
    });
    assert.equal(r.status,200);
    assert.equal(observed.cache,'no-store',`${method} ${path} must bypass the CDN cache`);
    assert.equal(observed.cf,undefined,'do not combine no-store with forced caching overrides');
    assert.equal(observed.redirect,'manual');
    assert.equal(r.headers.get('cache-control'),'no-store');
  }
});
test('login response cookie and form survive two separate browser round trips unchanged',async()=>{
  for(const letter of ['a','b']){
    const token=letter.repeat(43),proof=letter.repeat(64);
    const issued=`__Host-richon-oauth=${token}; Max-Age=600; HttpOnly; Path=/; SameSite=lax; Secure`;
    const html=`<form method="post" action="/auth/start"><input name="csrf" value="${proof}"></form>`;
    let getInit;
    const page=await handle(req(),env,async(url,init)=>{
      getInit=init;
      return new Response(html,{headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Set-Cookie':issued}});
    });
    assert.equal(page.status,200);assert.equal(getInit.cache,'no-store');
    assert.deepEqual(page.headers.getSetCookie(),[issued]);assert.equal(await page.text(),html);
    const browserCookie=page.headers.getSetCookie()[0].split(';')[0];
    const body=`csrf=${proof}&provider=kakao&return_to=%2Fportal%2Fmypage`;
    let posted;
    const response=await handle(req('/auth/start',{method:'POST',body,headers:{
      'Content-Type':'application/x-www-form-urlencoded',Origin:origin,'Sec-Fetch-Site':'same-origin',
      Cookie:`${browserCookie}; CF_Authorization=synthetic-access; unrelated=synthetic`
    }}),env,async(url,init)=>{
      posted=init;return new Response(null,{status:303,headers:{Location:'https://kauth.kakao.com/oauth/authorize?state=synthetic'}});
    });
    assert.equal(response.status,303);assert.equal(posted.headers.get('cookie'),browserCookie);
    assert.equal(posted.headers.get('origin'),origin);
    assert.equal(new TextDecoder().decode(posted.body),body);
    assert.equal(posted.cache,'no-store');assert.equal(response.headers.get('referrer-policy'),'no-referrer');
  }
});
test('provider callback preserves ticket issuance and separate cookie deletion headers',async()=>{
  const issued='__Host-richon-signup='+ 't'.repeat(43)+'; Max-Age=600; HttpOnly; Path=/; SameSite=lax; Secure';
  const deleted='__Host-richon-session=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; HttpOnly; Path=/; SameSite=lax; Secure';
  for(const provider of ['kakao','naver']){
    const headers=new Headers({Location:'/auth/signup','Cache-Control':'no-store'});
    headers.append('Set-Cookie',issued);headers.append('Set-Cookie',deleted);
    let observed;
    const r=await handle(req(`/auth/${provider}/callback?code=synthetic&state=synthetic`),env,async(url,init)=>{
      observed=init;return new Response(null,{status:303,headers});
    });
    assert.equal(r.status,303);assert.equal(observed.cache,'no-store');
    assert.equal(r.headers.get('location'),origin+'/auth/signup');
    assert.deepEqual(r.headers.getSetCookie(),[issued,deleted]);
    assert.equal(r.headers.get('referrer-policy'),'no-referrer');
  }
});
test('invalid login proof remains rejected; Worker must not invent a missing cookie or Origin',async()=>{
  let observed;
  const r=await handle(req('/auth/start',{method:'POST',body:'csrf=invalid&provider=kakao',headers:{
    'Content-Type':'application/x-www-form-urlencoded',Origin:'null'
  }}),env,async(url,init)=>{
    observed=init;return new Response('{"detail":"invalid_login_flow"}',{status:403,headers:{'Content-Type':'application/json'}});
  });
  assert.equal(observed.headers.get('cookie'),null);assert.equal(observed.headers.get('origin'),'null');
  assert.equal(observed.cache,'no-store');assert.equal(r.status,403);
  assert.equal(await r.text(),'{"detail":"invalid_login_flow"}');
  assert.equal(r.headers.get('set-cookie'),null);assert.equal(r.headers.get('referrer-policy'),'no-referrer');
});
