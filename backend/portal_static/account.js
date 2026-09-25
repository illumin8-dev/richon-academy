/* Authenticated own-account UI. No identity/session secrets in browser storage. */
'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const state={epoch:0,request:0,ready:false,offset:0,limit:20,more:false,me:null};
  const fields=['name','phone','email','age','gender'];
  const names={kakao:'카카오',naver:'네이버'};
  const ages={'14-19':'14~19세','20-29':'20~29세','30-39':'30~39세','40-49':'40~49세','50-59':'50~59세','60-69':'60~69세','70+':'70세 이상'};
  const genders={female:'여성',male:'남성'};
  const allowed=new Set(['/portal/api/me','/portal/api/me/orders','/portal/api/me/security','/portal/api/me/profile',
    '/portal/api/me/logins/link/pending','/portal/api/me/logins/link/confirm','/portal/api/me/logins/link/cancel',
    '/portal/api/me/withdraw/prepare','/portal/api/me/withdraw/status','/portal/api/me/withdraw/cancel',
    '/auth/csrf','/auth/logout']);
  const startPaths=new Set(['/portal/api/me/logins/link/start','/portal/api/me/reauth/start',
    '/portal/api/me/logins/unlink/start','/portal/api/me/withdraw/provider/start']);
  const text=(id,value)=>{if($(id))$(id).textContent=String(value??'');};
  const element=(tag,value,cls)=>{const el=document.createElement(tag);if(value!==undefined)el.textContent=String(value);if(cls)el.className=cls;return el;};
  const date=value=>{const d=new Date(value);return Number.isFinite(d.getTime())?new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Asia/Seoul'}).format(d):'확인 필요';};

  async function api(path,options={}) {
    const key=path.split('?')[0];
    if(!allowed.has(key))throw new Error('unsupported_path');
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,...options});
      if(!response.ok){
        const error=new Error('request_failed');error.status=response.status;
        try{const body=await response.json();if(body&&typeof body.detail==='string')error.detail=body.detail;}catch{}
        throw error;
      }
      return response.status===204?null:await response.json();
    }finally{clearTimeout(timer);}
  }

  async function csrfAction(path,method='POST',body=null){
    const proof=await api('/auth/csrf');
    const options={method,headers:{'X-CSRF-Token':proof.csrf_token}};
    if(body!==null){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
    return api(path,options);
  }

  async function nativeStart(path,provider){
    if(!startPaths.has(path)||!Object.hasOwn(names,provider))throw new Error('invalid_start');
    const proof=await api('/auth/csrf');
    const form=element('form');form.method='post';form.action=path;form.hidden=true;
    for(const [name,value] of [['csrf',proof.csrf_token],['provider',provider]]){
      const input=element('input');input.type='hidden';input.name=name;input.value=value;form.append(input);
    }
    document.body.append(form);form.submit();
  }

  function gate(title,message='',retry=false,login=false){
    state.epoch++;state.request++;state.ready=false;state.me=null;
    $('content').hidden=true;$('gate').hidden=false;$('logout').hidden=true;$('site-account-me').hidden=true;$('admin-link').hidden=true;
    $('list').replaceChildren();$('providers').replaceChildren();text('joined','');text('action-status','');text('list-status','');
    for(const field of fields){text('profile-'+field,'');$('profile-'+field+'-row').hidden=true;}
    $('edit-profile').hidden=true;$('manage-logins').hidden=true;$('withdraw-account').hidden=true;$('withdraw-inquiry').hidden=false;
    text('gate-title',title);text('gate-text',message);$('retry-gate').hidden=!retry;$('gate-login').hidden=!login;
  }

  function authError(error){
    if(error.status===401){gate('로그인이 필요합니다.','',false,true);return true;}
    if(error.status===403){gate('접근할 수 없습니다.','계정 상태를 확인해 주세요.');return true;}
    return false;
  }

  function profile(me){
    state.me=me;
    const data=me.registration;
    const registered=data&&typeof data.name==='string'&&typeof data.phone==='string'&&typeof data.email==='string';
    if(registered){
      for(const field of ['name','phone','email']){text('profile-'+field,data[field]);$('profile-'+field+'-row').hidden=false;}
      if(data.consultation_consent===true){
        for(const [field,dict,key] of [['age',ages,'age_range'],['gender',genders,'gender']]){
          if(Object.hasOwn(dict,data[key])){text('profile-'+field,dict[data[key]]);$('profile-'+field+'-row').hidden=false;}
        }
      }
    }
    text('joined',date(me.created_at));
    const visibleProviders=me.providers.filter(x=>Object.hasOwn(names,x));
    $('providers').replaceChildren(...visibleProviders.map(x=>element('span',names[x],'account-provider')));
    $('admin-link').hidden=me.role!=='admin';$('site-account-me').hidden=false;$('site-account-me').setAttribute('aria-current','page');
    const enabled=me.account_actions===true;
    $('edit-profile').hidden=!enabled||!registered;
    $('manage-logins').hidden=!enabled;
    $('withdraw-account').hidden=!enabled;
    $('withdraw-inquiry').hidden=enabled;
  }

  function render(items){
    $('list').replaceChildren();
    if(!items.length){
      const box=element('div',undefined,'account-empty');box.append(element('p','신청한 강의가 없습니다.'));
      const a=element('a','강의 둘러보기','site-btn site-btn-line');a.href='/#programs';box.append(a);$('list').append(box);return;
    }
    for(const row of items){
      const card=element('article',undefined,'account-course');const top=element('div',undefined,'account-course-top');const desc=element('div');
      desc.append(element('h3',row.course_title),element('div',(row.cohort?row.cohort+' / ':'')+'신청일 '+date(row.created_at),'account-meta'));
      top.append(desc,element('span',row.status==='pending_payment'?'결제 대기':'상태 확인 필요','account-badge'));card.append(top);
      const detail=element('details');detail.append(element('summary','주문 상세'),element('p','주문번호 '+row.order_id),element('p',new Intl.NumberFormat('ko-KR').format(row.amount_krw)+'원'));card.append(detail);$('list').append(card);
    }
  }

  async function list(){
    if(!state.ready)return;const epoch=state.epoch;const serial=++state.request;
    $('pager').hidden=true;$('retry-list').hidden=true;$('list').replaceChildren();text('list-status','불러오는 중입니다.');
    try{
      const rows=await api('/portal/api/me/orders?'+new URLSearchParams({limit:String(state.limit),offset:String(state.offset)}));
      if(epoch!==state.epoch||!state.ready||serial!==state.request)return;
      render(rows.items);text('list-status','');state.more=rows.has_more;$('pager').hidden=state.offset===0&&!state.more;
      $('prev').disabled=state.offset===0;$('next').disabled=!state.more||state.offset+state.limit>10000;
      text('page-info',rows.items.length?(String(state.offset+1)+'–'+String(state.offset+rows.items.length)):'');
    }catch(error){
      if(epoch!==state.epoch)return;if(authError(error))return;if(serial!==state.request)return;
      text('list-status','내역을 불러오지 못했습니다. 다시 시도해 주세요.');$('retry-list').hidden=false;
    }
  }

  function openDialog(id,focusId){
    const dialog=$(id);if(!dialog||typeof dialog.showModal!=='function')return;
    dialog.showModal();if(focusId)requestAnimationFrame(()=>$(focusId)?.focus());
  }
  function closeDialog(id){const dialog=$(id);if(dialog?.open)dialog.close();}
  document.querySelectorAll('[data-close-dialog]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog')?.close()));

  function setOptionalEnabled(){
    const enabled=$('edit-consultation').checked;
    $('edit-age').disabled=!enabled;$('edit-gender').disabled=!enabled;
  }

  $('edit-consultation').addEventListener('change',setOptionalEnabled);
  $('edit-profile').addEventListener('click',()=>{
    const data=state.me?.registration;if(!data)return;
    $('edit-name').value=data.name||'';$('edit-phone').value=data.phone||'';$('edit-email').value=data.email||'';
    $('edit-consultation').checked=data.consultation_consent===true;
    $('edit-age').value=Object.hasOwn(ages,data.age_range)?data.age_range:'';
    $('edit-gender').value=Object.hasOwn(genders,data.gender)?data.gender:'';
    text('profile-edit-status','');setOptionalEnabled();openDialog('profile-dialog','edit-name');
  });

  $('save-profile').addEventListener('click',async()=>{
    const consent=$('edit-consultation').checked;$('save-profile').disabled=true;text('profile-edit-status','');
    try{
      await csrfAction('/portal/api/me/profile','POST',{
        name:$('edit-name').value,phone:$('edit-phone').value,email:$('edit-email').value,
        age_range:consent?($('edit-age').value||null):null,
        gender:consent?($('edit-gender').value||null):null,
        consultation_consent:consent
      });
      closeDialog('profile-dialog');await boot();
    }catch(error){
      if(authError(error))closeDialog('profile-dialog');
      else text('profile-edit-status',error.status===422?'입력한 정보를 다시 확인해 주세요.':'저장하지 못했습니다. 다시 시도해 주세요.');
    }finally{$('save-profile').disabled=false;}
  });

  function renderLoginConnections(){
    const root=$('login-connections');root.replaceChildren();
    const linked=new Set(state.me?.providers||[]);
    for(const provider of ['kakao','naver']){
      const row=element('div',undefined,'account-login-row');const info=element('div');
      info.append(element('strong',names[provider]),element('div',linked.has(provider)?'연결됨':'연결 안 됨','account-login-meta'));
      const button=element('button',linked.has(provider)?(linked.size>1?'연결 해제':'현재 로그인 수단'):'연결','account-login-action');
      button.type='button';
      if(linked.has(provider)&&linked.size<=1)button.disabled=true;
      else if(linked.has(provider))button.addEventListener('click',()=>unlink(provider));
      else button.addEventListener('click',()=>startLink(provider));
      row.append(info,button);root.append(row);
    }
  }

  async function ensureFresh(){
    const result=await api('/portal/api/me/security');
    if(result.fresh_auth===true)return true;
    showProviderAuth('reauth',state.me?.providers||[]);return false;
  }

  function showProviderAuth(mode,values){
    closeDialog('login-dialog');closeDialog('withdraw-dialog');
    const withdrawing=mode==='withdraw';
    text('reauth-title',withdrawing?'회원탈퇴 본인 확인':'본인 확인');
    text('reauth-note',withdrawing
      ?'연결된 로그인 계정의 서비스 연동을 해제한 뒤 회원탈퇴를 완료합니다.'
      :'계정 연결을 변경하기 전에 연결된 로그인으로 한 번 더 확인합니다.');
    $('cancel-withdraw-flow').hidden=!withdrawing;
    const root=$('reauth-providers');root.replaceChildren();
    for(const provider of values||[]){
      if(!Object.hasOwn(names,provider))continue;
      const label=withdrawing?names[provider]+' 연동 해제 후 계속':names[provider]+'로 본인 확인';
      const button=element('button',label,'site-btn site-btn-line');button.type='button';
      button.addEventListener('click',()=>nativeStart(
        withdrawing?'/portal/api/me/withdraw/provider/start':'/portal/api/me/reauth/start',provider));
      root.append(button);
    }
    openDialog('reauth-dialog');
  }

  async function startLink(provider){
    text('login-action-status','');
    try{if(await ensureFresh())await nativeStart('/portal/api/me/logins/link/start',provider);}
    catch(error){if(!authError(error))text('login-action-status','연결을 시작하지 못했습니다. 다시 시도해 주세요.');}
  }

  async function unlink(provider){
    text('login-action-status','');
    try{
      if(!await ensureFresh())return;
      await nativeStart('/portal/api/me/logins/unlink/start',provider);
    }catch(error){
      if(error.status===409&&error.detail==='reauth_required'){showProviderAuth('reauth',state.me?.providers||[]);return;}
      if(error.status===409&&error.detail==='last_login_method'){text('login-action-status','마지막 로그인 수단은 해제할 수 없습니다.');return;}
      if(!authError(error))text('login-action-status','연결 해제를 시작하지 못했습니다. 다시 시도해 주세요.');
    }
  }

  $('manage-logins').addEventListener('click',()=>{text('login-action-status','');renderLoginConnections();openDialog('login-dialog');});

  async function pendingLink(){
    if(state.me?.account_actions!==true)return;
    try{
      const pending=await api('/portal/api/me/logins/link/pending');
      if(!pending||!Object.hasOwn(names,pending.provider))return;
      text('link-confirm-provider',names[pending.provider]);text('link-confirm-status','');openDialog('link-confirm-dialog','confirm-link');
    }catch(error){if(!authError(error))text('action-status','로그인 연결 상태를 확인하지 못했습니다.');}
  }

  $('confirm-link').addEventListener('click',async()=>{
    $('confirm-link').disabled=true;text('link-confirm-status','');
    try{await csrfAction('/portal/api/me/logins/link/confirm');closeDialog('link-confirm-dialog');await boot();}
    catch(error){
      if(error.status===409&&error.detail==='identity_already_in_use')text('link-confirm-status','이미 다른 회원에 연결된 로그인입니다.');
      else if(!authError(error))text('link-confirm-status','연결하지 못했습니다. 다시 시도해 주세요.');
    }finally{$('confirm-link').disabled=false;}
  });
  $('cancel-link').addEventListener('click',async()=>{
    $('cancel-link').disabled=true;
    try{await csrfAction('/portal/api/me/logins/link/cancel');closeDialog('link-confirm-dialog');}
    catch(error){if(!authError(error))text('link-confirm-status','취소하지 못했습니다. 다시 시도해 주세요.');}
    finally{$('cancel-link').disabled=false;}
  });

  $('withdraw-account').addEventListener('click',()=>{$('withdraw-confirm').value='';text('withdraw-status','');openDialog('withdraw-dialog','withdraw-confirm');});
  $('confirm-withdraw').addEventListener('click',async()=>{
    $('confirm-withdraw').disabled=true;text('withdraw-status','');
    try{
      const result=await csrfAction('/portal/api/me/withdraw/prepare','POST',{confirm:$('withdraw-confirm').value});
      closeDialog('withdraw-dialog');
      showProviderAuth('withdraw',result.providers||[]);
    }catch(error){
      if(error.status===409&&error.detail==='reauth_required'){showProviderAuth('reauth',state.me?.providers||[]);return;}
      if(error.status===422){text('withdraw-status','확인 문구를 정확히 입력해 주세요.');return;}
      if(error.status===503&&error.detail==='withdrawal_cleanup_not_ready'){text('withdraw-status','현재 탈퇴 처리를 완료할 수 없습니다. 고객센터로 문의해 주세요.');return;}
      if(!authError(error))text('withdraw-status','탈퇴를 시작하지 못했습니다. 다시 시도해 주세요.');
    }finally{$('confirm-withdraw').disabled=false;}
  });

  $('cancel-withdraw-flow').addEventListener('click',async()=>{
    $('cancel-withdraw-flow').disabled=true;
    try{await csrfAction('/portal/api/me/withdraw/cancel');closeDialog('reauth-dialog');await boot();}
    catch(error){if(!authError(error))text('action-status','탈퇴 절차를 중단하지 못했습니다. 다시 시도해 주세요.');}
    finally{$('cancel-withdraw-flow').disabled=false;}
  });

  async function resumeWithdrawal(){
    if(state.me?.account_actions!==true)return;
    try{
      const result=await api('/portal/api/me/withdraw/status');
      if(result&&Array.isArray(result.providers)&&result.providers.length){
        showProviderAuth('withdraw',result.providers);
      }
    }catch(error){if(!authError(error))text('action-status','진행 중인 탈퇴 상태를 확인하지 못했습니다.');}
  }

  async function accountNotice(){
    if(state.me?.account_actions!==true)return;
    try{
      const result=await api('/portal/api/me/security');
      if(result.provider_unlink_failed===true){
        text('action-status','이전 로그인 연동 해제를 완료하지 못했습니다. 다시 시도해 주세요.');
      }
    }catch(error){if(!authError(error))text('action-status','');}
  }

  async function boot(){
    gate('로그인 확인 중');const epoch=state.epoch;
    try{
      const me=await api('/portal/api/me');if(epoch!==state.epoch)return;
      profile(me);state.ready=true;$('gate').hidden=true;$('content').hidden=false;$('logout').hidden=false;
      await list();await pendingLink();await accountNotice();await resumeWithdrawal();
    }catch(error){if(epoch!==state.epoch)return;if(!authError(error))gate('정보를 불러오지 못했습니다.','잠시 후 다시 확인해 주세요.',true);}
  }

  $('retry-gate').addEventListener('click',boot);$('refresh').addEventListener('click',list);$('retry-list').addEventListener('click',list);
  $('prev').addEventListener('click',()=>{if(state.offset>0){state.offset-=state.limit;list();}});
  $('next').addEventListener('click',()=>{if(state.more&&state.offset+state.limit<=10000){state.offset+=state.limit;list();}});
  $('logout').addEventListener('click',async()=>{
    if(!state.ready)return;const epoch=state.epoch;$('logout').disabled=true;
    try{await csrfAction('/auth/logout');if(epoch===state.epoch)gate('로그아웃되었습니다.','',false,true);}
    catch(error){if(epoch===state.epoch&&!authError(error))text('action-status','로그아웃하지 못했습니다. 다시 시도해 주세요.');}
    finally{$('logout').disabled=false;}
  });
  window.addEventListener('pageshow',event=>{if(event.persisted)boot();});
  window.addEventListener('pagehide',()=>gate('로그인 확인 중'));
  boot();
})();
