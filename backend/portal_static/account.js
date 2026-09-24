/* Authenticated, own-account UI only. No customer data or session tokens in browser storage. */
'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const state={epoch:0,request:0,ready:false,offset:0,limit:20,more:false};
  const fields=['name','phone','email','age','gender'];
  const names={kakao:'카카오',naver:'네이버'};
  const ages={'14-19':'14~19세','20-29':'20~29세','30-39':'30~39세','40-49':'40~49세','50-59':'50~59세','60-69':'60~69세','70+':'70세 이상'};
  const genders={female:'여성',male:'남성'};
  const text=(id,value)=>{$(id).textContent=String(value??'');};
  const element=(tag,value,cls)=>{const el=document.createElement(tag);if(value!==undefined)el.textContent=String(value);if(cls)el.className=cls;return el;};
  const date=value=>{const d=new Date(value);return Number.isFinite(d.getTime())?new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Asia/Seoul'}).format(d):'확인 필요';};
  async function api(path,options={}) {
    if(!['/portal/api/me','/portal/api/me/orders','/auth/csrf','/auth/logout'].includes(path.split('?')[0]))throw new Error('unsupported_path');
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
    try{const r=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,...options});if(!r.ok){const e=new Error('request_failed');e.status=r.status;throw e;}return r.status===204?null:await r.json();}finally{clearTimeout(timer);}
  }
  function gate(title,message='',retry=false,login=false){
    state.epoch++;state.request++;state.ready=false;
    $('content').hidden=true;$('gate').hidden=false;$('logout').hidden=true;$('site-account-me').hidden=true;$('admin-link').hidden=true;
    $('list').replaceChildren();$('providers').replaceChildren();text('joined','');text('action-status','');text('list-status','');
    for(const field of fields){text('profile-'+field,'');$('profile-'+field+'-row').hidden=true;}
    text('gate-title',title);text('gate-text',message);$('retry-gate').hidden=!retry;$('gate-login').hidden=!login;
  }
  function authError(e){if(e.status===401){gate('로그인이 필요합니다.','',false,true);return true;}if(e.status===403){gate('접근할 수 없습니다.','계정 상태를 확인해 주세요.');return true;}return false;}
  function profile(me){
    const data=me.registration;
    if(data&&typeof data.name==='string'&&typeof data.phone==='string'&&typeof data.email==='string'){
      for(const field of ['name','phone','email']){text('profile-'+field,data[field]);$('profile-'+field+'-row').hidden=false;}
      if(data.consultation_consent===true){for(const [field,dict,key] of [['age',ages,'age_range'],['gender',genders,'gender']]){if(Object.hasOwn(dict,data[key])){text('profile-'+field,dict[data[key]]);$('profile-'+field+'-row').hidden=false;}}}
    }
    // Never use provider fallback nicknames as a real name or create a greeting.
    text('joined',date(me.created_at));
    $('providers').replaceChildren(...me.providers.filter(x=>Object.hasOwn(names,x)).map(x=>element('span',names[x],'account-provider')));
    $('admin-link').hidden=me.role!=='admin';$('site-account-me').hidden=false;$('site-account-me').setAttribute('aria-current','page');
  }
  function render(items){
    $('list').replaceChildren();
    if(!items.length){const box=element('div',undefined,'account-empty');box.append(element('p','신청한 강의가 없습니다.'));const a=element('a','강의 둘러보기','site-btn site-btn-line');a.href='/#programs';box.append(a);$('list').append(box);return;}
    for(const row of items){
      const card=element('article',undefined,'account-course');const top=element('div',undefined,'account-course-top');const desc=element('div');desc.append(element('h3',row.course_title),element('div',(row.cohort?row.cohort+' / ':'')+'신청일 '+date(row.created_at),'account-meta'));
      top.append(desc,element('span',row.status==='pending_payment'?'결제 대기':'상태 확인 필요','account-badge'));card.append(top);
      const detail=element('details');detail.append(element('summary','주문 상세'),element('p','주문번호 '+row.order_id),element('p',new Intl.NumberFormat('ko-KR').format(row.amount_krw)+'원'));card.append(detail);$('list').append(card);
    }
  }
  async function list(){
    if(!state.ready)return;const epoch=state.epoch;const serial=++state.request;
    $('pager').hidden=true;$('retry-list').hidden=true;$('list').replaceChildren();text('list-status','불러오는 중입니다.');
    try{const rows=await api('/portal/api/me/orders?'+new URLSearchParams({limit:String(state.limit),offset:String(state.offset)}));if(epoch!==state.epoch||!state.ready||serial!==state.request)return;render(rows.items);text('list-status','');state.more=rows.has_more;$('pager').hidden=state.offset===0&&!state.more;$('prev').disabled=state.offset===0;$('next').disabled=!state.more||state.offset+state.limit>10000;text('page-info',rows.items.length?`${state.offset+1}–${state.offset+rows.items.length}`:'');}
    catch(e){if(epoch!==state.epoch)return;if(authError(e))return;if(serial!==state.request)return;text('list-status','내역을 불러오지 못했습니다. 다시 시도해 주세요.');$('retry-list').hidden=false;}
  }
  async function boot(){gate('로그인 확인 중');const epoch=state.epoch;try{const me=await api('/portal/api/me');if(epoch!==state.epoch)return;profile(me);state.ready=true;$('gate').hidden=true;$('content').hidden=false;$('logout').hidden=false;await list();}catch(e){if(epoch!==state.epoch)return;if(!authError(e))gate('정보를 불러오지 못했습니다.','잠시 후 다시 확인해 주세요.',true);}}
  $('retry-gate').addEventListener('click',boot);$('refresh').addEventListener('click',list);$('retry-list').addEventListener('click',list);
  $('prev').addEventListener('click',()=>{if(state.offset>0){state.offset-=state.limit;list();}});$('next').addEventListener('click',()=>{if(state.more&&state.offset+state.limit<=10000){state.offset+=state.limit;list();}});
  $('logout').addEventListener('click',async()=>{if(!state.ready)return;const epoch=state.epoch;$('logout').disabled=true;try{const csrf=await api('/auth/csrf');if(epoch!==state.epoch)return;await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf.csrf_token}});if(epoch===state.epoch)gate('로그아웃되었습니다.','',false,true);}catch(e){if(epoch===state.epoch&&!authError(e))text('action-status','로그아웃하지 못했습니다. 다시 시도해 주세요.');}finally{$('logout').disabled=false;}});
  window.addEventListener('pageshow',e=>{if(e.persisted)boot();});window.addEventListener('pagehide',()=>gate('로그인 확인 중'));boot();
})();
