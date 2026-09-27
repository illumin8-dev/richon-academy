/* Provider navigation starts only after the same-origin form POST has completed. */
'use strict';
(() => {
  const link=document.querySelector('[data-richon-provider-handoff]');
  if(!link)return;
  let url;
  try{url=new URL(link.href);}catch{return;}
  const allowed=(url.protocol==='https:'&&!url.username&&!url.password&&!url.port&&!url.hash)&&(
    (url.hostname==='kauth.kakao.com'&&url.pathname==='/oauth/authorize')||
    (url.hostname==='nid.naver.com'&&url.pathname==='/oauth2.0/authorize')
  );
  if(!allowed)return;
  window.location.replace(url.href);
})();
