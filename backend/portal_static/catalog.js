/* Course catalog admin UI. Same-origin only; no tokens or identity stored in browser storage. */
'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const state={programs:[],runs:[],sessions:[],program:null,run:null,editingProgram:null,editingRun:null,editingSession:null};
  const statusLabel={UPCOMING:'모집 예정',OPEN:'모집 중',WAITLIST:'대기 신청',CLOSED:'마감'};
  const text=(id,v)=>{if($(id))$(id).textContent=String(v??'');};
  const el=(tag,value,cls)=>{const node=document.createElement(tag);if(value!==undefined)node.textContent=String(value);if(cls)node.className=cls;return node;};
  function errorOf(response){const e=new Error('request_failed');e.status=response.status;return e;}
  async function api(path,options={}){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,...options});
      if(!response.ok)throw errorOf(response);
      return response.status===204?null:await response.json();
    }finally{clearTimeout(timer);}
  }
  async function write(path,body){
    const csrf=await api('/auth/csrf');
    return api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf.csrf_token},body:JSON.stringify(body)});
  }
  function authError(e){
    if(e.status===401){gate('로그인이 필요합니다.','관리자 계정으로 다시 로그인해 주세요.',false);return true;}
    if(e.status===403){gate('관리자만 이용할 수 있습니다.','관리자 권한이 있는 계정으로 로그인해 주세요.',false);return true;}
    return false;
  }
  function gate(title,note,retry){
    $('content').hidden=true;$('gate').hidden=false;$('logout').hidden=true;text('gate-title',title);text('gate-note',note);$('retry').hidden=!retry;
  }
  function open(id,focus){const d=$(id);if(!d.open)d.showModal();if(focus)setTimeout(()=>d.querySelector(focus)?.focus(),0);}
  function close(id){const d=$(id);if(d.open)d.close();}
  document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>close(b.dataset.close)));

  function statusBadge(status){
    const cls=status==='OPEN'?'open':status==='WAITLIST'?'wait':status==='CLOSED'?'closed':'';
    return el('span',statusLabel[status]||status,'catalog-badge '+cls);
  }
  function card(title,meta,badge,selected,onSelect,onEdit){
    const root=el('div',undefined,'catalog-card'+(selected?' selected':''));root.tabIndex=0;root.setAttribute('role','button');
    const top=el('div',undefined,'catalog-card-top');top.append(el('div',title,'catalog-card-title'));if(badge)top.append(badge);
    root.append(top,el('div',meta,'catalog-card-meta'));
    const actions=el('div',undefined,'catalog-actions'),edit=el('button','수정','catalog-edit');edit.type='button';
    edit.addEventListener('click',ev=>{ev.stopPropagation();onEdit();});actions.append(edit);root.append(actions);
    root.addEventListener('click',onSelect);root.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();onSelect();}});
    return root;
  }
  function empty(root,message){root.replaceChildren(el('div',message,'catalog-empty'));}

  function renderPrograms(){
    const root=$('program-list');root.replaceChildren();
    if(!state.programs.length){empty(root,'등록된 프로그램이 없습니다.');return;}
    for(const p of state.programs){
      const meta=(p.access_kind==='fixed_months'?p.fixed_months+'개월 고정':'기간 지정')+(p.archived?' / 보관됨':'');
      root.append(card(p.title,meta,p.archived?el('span','보관','catalog-badge'):null,state.program?.program_id===p.program_id,
        ()=>selectProgram(p),()=>editProgram(p)));
    }
  }
  function renderRuns(){
    const root=$('run-list');root.replaceChildren();
    if(!state.program){empty(root,'프로그램을 먼저 선택하세요.');return;}
    if(!state.runs.length){empty(root,'등록된 기수가 없습니다.');return;}
    for(const r of state.runs){
      const meta=(r.cohort||'기수명 없음')+' / '+r.starts_on+' ~ '+r.ends_on+(r.archived?' / 보관됨':'');
      root.append(card(state.program.title,meta,statusBadge(r.status),state.run?.run_id===r.run_id,
        ()=>selectRun(r),()=>editRun(r)));
    }
  }
  function formatKst(value){if(!value)return '';return new Intl.DateTimeFormat('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Seoul'}).format(new Date(value));}
  function renderSessions(){
    const root=$('session-list');root.replaceChildren();
    if(!state.run){empty(root,'기수를 먼저 선택하세요.');return;}
    if(!state.sessions.length){empty(root,'등록된 회차가 없습니다.');return;}
    for(const s of state.sessions){
      const meta=formatKst(s.starts_at)+' / '+(s.mentor_name||'담당 멘토 미정')+(s.archived?' / 보관됨':'');
      root.append(card(s.sequence_no+'주차 · '+s.title,meta,null,false,()=>{},()=>editSession(s)));
    }
  }
  async function loadPrograms(){
    text('program-status','불러오는 중');
    try{state.programs=await api('/portal/api/admin/catalog/programs?include_archived=true');text('program-status','');renderPrograms();}
    catch(e){if(!authError(e))text('program-status','프로그램을 불러오지 못했습니다.');}
  }
  async function selectProgram(p){
    state.program=p;state.run=null;state.sessions=[];renderPrograms();renderSessions();$('new-run').disabled=false;
    text('run-context',p.title);text('session-context','기수를 선택하세요.');text('run-status','불러오는 중');
    try{state.runs=await api('/portal/api/admin/catalog/runs?include_archived=true&program_id='+encodeURIComponent(p.program_id));text('run-status','');renderRuns();}
    catch(e){if(!authError(e))text('run-status','기수를 불러오지 못했습니다.');}
  }
  async function selectRun(r){
    state.run=r;renderRuns();$('new-session').disabled=false;text('session-context',(r.cohort||state.program.title)+' / '+statusLabel[r.status]);text('session-status','불러오는 중');
    try{state.sessions=await api('/portal/api/admin/catalog/runs/'+encodeURIComponent(r.run_id)+'/sessions?include_archived=true');text('session-status','');renderSessions();}
    catch(e){if(!authError(e))text('session-status','회차를 불러오지 못했습니다.');}
  }
  function value(form,name){return form.elements[name].value.trim();}
  function nullable(form,name){const v=value(form,name);return v||null;}
  function numberOrNull(form,name){const v=value(form,name);return v?Number(v):null;}
  function isoOrNull(form,name){const v=value(form,name);if(!v)return null;const d=new Date(v);return Number.isFinite(d.getTime())?d.toISOString():null;}
  function localInput(v){if(!v)return '';const d=new Date(v);const parts=new Intl.DateTimeFormat('sv-SE',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Seoul'}).formatToParts(d);const m=Object.fromEntries(parts.map(x=>[x.type,x.value]));return m.year+'-'+m.month+'-'+m.day+'T'+m.hour+':'+m.minute;}
  function inclusiveEnd(start,months){
    if(!start||!months)return '';const [y,m,d]=start.split('-').map(Number);const x=new Date(Date.UTC(y,m-1,d));x.setUTCMonth(x.getUTCMonth()+Number(months));x.setUTCDate(x.getUTCDate()-1);return x.toISOString().slice(0,10);
  }
  function syncProgramPolicy(){
    const f=$('program-form'),fixed=value(f,'access_kind')==='fixed_months';$('fixed-months-field').hidden=!fixed;f.elements.fixed_months.required=fixed;
  }
  $('program-form').elements.access_kind.addEventListener('change',syncProgramPolicy);
  function syncRunAccess(){
    if(!state.program)return;const f=$('run-form');
    if(state.program.access_kind==='fixed_months'){
      text('run-access-help',state.program.fixed_months+'개월 고정형: 수강 시작일을 기준으로 종료일을 자동 계산합니다.');
      const end=inclusiveEnd(value(f,'default_access_start'),state.program.fixed_months);if(end)f.elements.default_access_end.value=end;f.elements.default_access_end.readOnly=true;
    }else{text('run-access-help','기간 지정형: 수강 시작일과 종료일을 직접 입력합니다.');f.elements.default_access_end.readOnly=false;}
  }
  $('run-form').elements.default_access_start.addEventListener('change',syncRunAccess);

  function newProgram(){
    state.editingProgram=null;const f=$('program-form');f.reset();f.elements.fixed_months.value='2';$('program-archive-field').hidden=true;text('program-dialog-title','프로그램 추가');text('program-error','');syncProgramPolicy();open('program-dialog','input[name=title]');
  }
  function editProgram(p){
    state.editingProgram=p;const f=$('program-form');f.reset();f.elements.title.value=p.title;f.elements.description.value=p.description||'';f.elements.access_kind.value=p.access_kind;f.elements.fixed_months.value=p.fixed_months||'';f.elements.archived.checked=p.archived;$('program-archive-field').hidden=false;text('program-dialog-title','프로그램 수정');text('program-error','');syncProgramPolicy();open('program-dialog','input[name=title]');
  }
  $('new-program').addEventListener('click',newProgram);
  $('program-form').addEventListener('submit',async ev=>{
    ev.preventDefault();const f=ev.currentTarget,editing=state.editingProgram;
    const body={request_id:crypto.randomUUID(),reason:value(f,'reason'),title:value(f,'title'),description:nullable(f,'description'),access_kind:value(f,'access_kind'),fixed_months:value(f,'access_kind')==='fixed_months'?Number(value(f,'fixed_months')):null};
    if(editing)Object.assign(body,{program_id:editing.program_id,version:editing.version,archived:f.elements.archived.checked});
    try{await write(editing?'/portal/api/admin/catalog/programs/update':'/portal/api/admin/catalog/programs',body);close('program-dialog');state.program=null;state.run=null;state.runs=[];state.sessions=[];$('new-run').disabled=true;$('new-session').disabled=true;await loadPrograms();renderRuns();renderSessions();}
    catch(e){if(!authError(e))text('program-error',e.status===409?'다른 변경이 먼저 반영됐습니다. 목록을 새로 확인해 주세요.':'저장하지 못했습니다. 입력값을 확인해 주세요.');}
  });

  function fillRun(f,r){
    f.elements.cohort.value=r?.cohort||'';f.elements.status.value=r?.status||'UPCOMING';f.elements.starts_on.value=r?.starts_on||'';f.elements.ends_on.value=r?.ends_on||'';f.elements.default_access_start.value=r?.default_access_start||'';f.elements.default_access_end.value=r?.default_access_end||'';f.elements.recruitment_open_at.value=localInput(r?.recruitment_open_at);f.elements.recruitment_close_at.value=localInput(r?.recruitment_close_at);f.elements.capacity.value=r?.capacity||'';f.elements.price_krw.value=r?.price_krw??0;f.elements.archived.checked=r?.archived||false;
  }
  function newRun(){if(!state.program)return;state.editingRun=null;const f=$('run-form');f.reset();fillRun(f,null);$('run-archive-field').hidden=true;text('run-dialog-title','기수 추가');text('run-error','');syncRunAccess();open('run-dialog','input[name=cohort]');}
  function editRun(r){state.editingRun=r;const f=$('run-form');f.reset();fillRun(f,r);$('run-archive-field').hidden=false;text('run-dialog-title','기수 수정');text('run-error','');syncRunAccess();open('run-dialog','input[name=cohort]');}
  $('new-run').addEventListener('click',newRun);
  $('run-form').addEventListener('submit',async ev=>{
    ev.preventDefault();if(!state.program)return;const f=ev.currentTarget,editing=state.editingRun;
    const body={request_id:crypto.randomUUID(),reason:value(f,'reason'),cohort:nullable(f,'cohort'),status:value(f,'status'),starts_on:value(f,'starts_on'),ends_on:value(f,'ends_on'),default_access_start:value(f,'default_access_start'),default_access_end:value(f,'default_access_end'),recruitment_open_at:isoOrNull(f,'recruitment_open_at'),recruitment_close_at:isoOrNull(f,'recruitment_close_at'),capacity:numberOrNull(f,'capacity'),price_krw:Number(value(f,'price_krw')||0)};
    if(editing)Object.assign(body,{run_id:editing.run_id,version:editing.version,archived:f.elements.archived.checked});else body.program_id=state.program.program_id;
    try{await write(editing?'/portal/api/admin/catalog/runs/update':'/portal/api/admin/catalog/runs',body);close('run-dialog');const selected=state.program;state.run=null;state.sessions=[];$('new-session').disabled=true;await selectProgram(selected);}
    catch(e){if(!authError(e))text('run-error',e.status===409?'다른 변경이 먼저 반영됐습니다.':'저장하지 못했습니다. 날짜와 수강기간을 확인해 주세요.');}
  });

  function fillSession(f,s){
    f.elements.sequence_no.value=s?.sequence_no||state.sessions.length+1;f.elements.title.value=s?.title||'';f.elements.mentor_name.value=s?.mentor_name||'';f.elements.starts_at.value=localInput(s?.starts_at);f.elements.ends_at.value=localInput(s?.ends_at);f.elements.content_url.value=s?.content_url||'';f.elements.archived.checked=s?.archived||false;
  }
  function newSession(){if(!state.run)return;state.editingSession=null;const f=$('session-form');f.reset();fillSession(f,null);$('session-archive-field').hidden=true;text('session-dialog-title','회차 추가');text('session-error','');open('session-dialog','input[name=sequence_no]');}
  function editSession(s){state.editingSession=s;const f=$('session-form');f.reset();fillSession(f,s);$('session-archive-field').hidden=false;text('session-dialog-title','회차 수정');text('session-error','');open('session-dialog','input[name=title]');}
  $('new-session').addEventListener('click',newSession);
  $('session-form').addEventListener('submit',async ev=>{
    ev.preventDefault();if(!state.run)return;const f=ev.currentTarget,editing=state.editingSession;
    const body={request_id:crypto.randomUUID(),reason:value(f,'reason'),sequence_no:Number(value(f,'sequence_no')),title:value(f,'title'),mentor_name:nullable(f,'mentor_name'),starts_at:isoOrNull(f,'starts_at'),ends_at:isoOrNull(f,'ends_at'),content_url:nullable(f,'content_url')};
    if(editing)Object.assign(body,{session_id:editing.session_id,version:editing.version,archived:f.elements.archived.checked});else body.run_id=state.run.run_id;
    try{await write(editing?'/portal/api/admin/catalog/sessions/update':'/portal/api/admin/catalog/sessions',body);close('session-dialog');const selected=state.run;await selectRun(selected);}
    catch(e){if(!authError(e))text('session-error',e.status===409?'순서가 중복되었거나 다른 변경이 먼저 반영됐습니다.':'저장하지 못했습니다. 일시와 링크를 확인해 주세요.');}
  });

  $('retry').addEventListener('click',boot);
  $('logout').addEventListener('click',async()=>{try{const csrf=await api('/auth/csrf');await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf.csrf_token}});gate('로그아웃되었습니다.','',false);}catch(e){text('page-status','로그아웃하지 못했습니다.');}});
  async function boot(){
    gate('관리자 권한을 확인하고 있습니다.','잠시만 기다려 주세요.',false);
    try{const me=await api('/portal/api/me');if(me.role!=='admin'){gate('관리자만 이용할 수 있습니다.','관리자 계정으로 로그인해 주세요.',false);return;}$('gate').hidden=true;$('content').hidden=false;$('logout').hidden=false;await loadPrograms();renderRuns();renderSessions();}
    catch(e){if(!authError(e))gate('강의 관리를 불러오지 못했습니다.','연결 상태를 확인한 후 다시 시도해 주세요.',true);}
  }
  boot();
})();
