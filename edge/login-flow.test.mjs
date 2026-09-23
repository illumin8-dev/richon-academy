import test from 'node:test';
import assert from 'node:assert/strict';
import {allowed, handle, safeLocation, returnReferer, responseReferrerPolicy} from './worker.mjs';
const ORIGIN='https://richonacademy.com';
const env={PORTAL_ENABLED:'true',PORTAL_UPSTREAM:'https://richon-portal-example-as.a.run.app',RICHON_EDGE_SECRET:'S'.repeat(43)};

test('form documents get same-origin; callback/error/asset responses stay no-referrer',()=>{
  for(const path of ['/auth/login','/auth/signup']) assert.equal(responseReferrerPolicy(path,'GET',200,'text/html; charset=utf-8'),'same-origin');
  for(const [path,method,status,type] of [['/auth/login','POST',200,'text/html'],['/auth/login','GET',422,'text/html'],['/auth/kakao/callback','GET',303,'text/html'],['/auth/assets/kakao-login.png','GET',200,'image/png'],['/portal/mypage','GET',200,'text/html']]) assert.equal(responseReferrerPolicy(path,method,status,type),'no-referrer');
});
test('prior-page hint is exact same-origin and discards query/fragment',()=>{
  for(const path of ['/','/index.html','/apply.html','/portal/mypage']) assert.equal(returnReferer(ORIGIN+path+'?code=do-not-forward#fragment'),ORIGIN+path);
  for(const value of [null,'https://evil.invalid/apply.html',ORIGIN+'.evil.invalid/apply.html',ORIGIN+'/portal/../apply.html',ORIGIN+'/%61pply.html',ORIGIN+'/auth/login','https://user@richonacademy.com/apply.html']) assert.equal(returnReferer(value),null);
});
test('public returns allowed only at login completion, no external/query/traversal/loops',()=>{
  for(const source of ['/auth/kakao/callback','/auth/naver/callback','/auth/signup']) for(const path of ['/','/index.html','/apply.html']) assert.equal(safeLocation(path,source),ORIGIN+path);
  for(const value of ['https://evil.invalid/','//evil.invalid/','/apply.html?code=x','/apply.html#x','/portal/../apply.html','/%61pply.html']) assert.throws(()=>safeLocation(value,'/auth/kakao/callback'));
  assert.throws(()=>safeLocation('/apply.html','/auth/start'));
  assert.equal(safeLocation('/auth/signup','/auth/kakao/callback'),ORIGIN+'/auth/signup');
});
test('new public destinations never become proxy request routes; asset exact GET only',()=>{
  for(const path of ['/','/index.html','/apply.html','/auth/assets/unknown.png']) assert.equal(allowed(path,'GET'),false);
  assert.equal(allowed('/auth/assets/kakao-login.png','GET'),true);assert.equal(allowed('/auth/assets/kakao-login.png','POST'),false);
});
test('actual proxy preserves supplied Origin, sanitizes only login GET Referer',async()=>{
  let seen;
  const transport=async(url,args)=>{seen=args;return new Response('<form></form>',{headers:{'Content-Type':'text/html; charset=utf-8'}})};
  const response=await handle(new Request(ORIGIN+'/auth/login',{headers:{Referer:ORIGIN+'/apply.html?discard=x'}}),env,transport);
  assert.equal(response.headers.get('referrer-policy'),'same-origin');assert.equal(seen.headers.get('referer'),ORIGIN+'/apply.html');assert.equal(seen.headers.get('origin'),null);
  await handle(new Request(ORIGIN+'/auth/start',{method:'POST',headers:{Origin:'null',Referer:ORIGIN+'/apply.html'},body:'csrf=synthetic'}),env,transport);
  assert.equal(seen.headers.get('origin'),'null');assert.equal(seen.headers.get('referer'),null);
  const redirect=await handle(new Request(ORIGIN+'/auth/kakao/callback'),env,async()=>new Response(null,{status:303,headers:{Location:'/apply.html'}}));
  assert.equal(redirect.headers.get('location'),ORIGIN+'/apply.html');assert.equal(redirect.headers.get('referrer-policy'),'no-referrer');assert.equal(redirect.headers.get('cache-control'),'no-store');
});
