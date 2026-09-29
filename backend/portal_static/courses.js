'use strict';
(()=>{
const $=id=>document.getElementById(id);
const state={programs:[],runs:[],selected:null,loginPrompted:false};
const text=(id,v)=>{if($(id))$(id).textContent=String(v??'');};
const el=(tag,value,cls)=>{const x=document.createElement(tag);if(value!==undefined)x.textContent=String(value);if(cls)x.className=cls;return x;};
const requestId=()=>crypto.randomUUID();
async function api(path,options={}){
 const r=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',...options});
 if(!r.ok){const e=new Error('request_failed');e.status=r.status;try{e.detail=(await r.json()).detail}catch{}throw e;}
 return r.status===204?null:r.json();
}
async function csrf(){
 const r=await api('/auth/csrf');return r.csrf_token;
}
async function post(path,body){
 const token=await csrf();
 return api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(body)});
}
const date=v=>v||'—';
const money=v=>new Intl.NumberFormat('ko-KR').format(v||0)+'원';
function formData(form){
 const d=Object.fromEntries(new FormData(form));
 for(const k of Object.keys(d))if(d[k]==='')d[k]=null;
 return d;
}
function isoLocal(v){return v?new Date(v).toISOString():null;}
function fillSelect(select,items,label){
 select.replaceChildren();
 const blank=el('option',label);blank.value='';select.append(blank);
 for(const item of items){const o=el('option',item.label);o.value=item.value;select.append(o);}
}
function catalogOptions(){
 const ps=state.programs.filter(x=>!x.archived).map(x=>({value:x.program_id,label:x.title}));
 fillSelect($('run-program'),ps,'프로그램 선택');
 const rs=state.runs.filter(x=>!x.archived).map(x=>({value:x.run_id,label:x.program_title+(x.cohort_label?' / '+x.cohort_label:'')}));
 for(const id of ['grant-run','session-run'])fillSelect($(id),rs,'기수 선택');
 fillSelect($('enrollment-run'),[{value:'',label:'전체 기수'},...rs],'전체 기수');
 loadSessions();
}
function renderCatalog(){
 $('program-list').replaceChildren(...state.programs.map(p=>el('span',p.title+(p.fixed_months?' / '+p.fixed_months+'개월':''),'program-chip')));
 $('run-list').replaceChildren();
 for(const r of state.runs){
  const row=el('div',undefined,'run-card');
  const info=el('div');info.append(el('strong',r.program_title+(r.cohort_label?' / '+r.cohort_label:'')),el('small',date(r.starts_on)+' ~ '+date(r.ends_on)));
  const status=el('select');for(const x of ['UPCOMING','OPEN','WAITLIST','CLOSED']){const o=el('option',x);o.value=x;o.selected=x===r.status;status.append(o);}
  const price=el('input');price.type='number';price.min='0';price.value=String(r.price_krw);
  const cap=el('input');cap.type='number';cap.min='1';cap.placeholder='정원';cap.value=r.capacity??'';
  const count=el('span',(r.enrollment_count||0)+'명');
  const save=el('button','변경 저장');save.type='button';save.addEventListener('click',async()=>{
   save.disabled=true;
   try{
    await post('/portal/api/admin/learning/runs/update',{request_id:requestId(),reason:'관리자 기수 정보 수정',run_id:r.run_id,version:r.version,
      cohort_label:r.cohort_label,recruit_opens_at:r.recruit_opens_at,recruit_closes_at:r.recruit_closes_at,
      capacity:cap.value?Number(cap.value):null,status:status.value,price_krw:Number(price.value||0),archived:false});
    text('catalog-status','저장했습니다.');await loadCatalog();
   }catch(e){text('catalog-status','저장하지 못했습니다: '+(e.detail||e.status||''));}finally{save.disabled=false;}
  });
  row.append(info,status,price,cap,count,save);$('run-list').append(row);
 }
}
async function loadCatalog(){
 text('catalog-status','불러오는 중입니다.');
 const [p,r]=await Promise.all([api('/portal/api/admin/learning/programs'),api('/portal/api/admin/learning/runs')]);
 state.programs=p.items;state.runs=r.items;renderCatalog();catalogOptions();text('catalog-status','');await loadEnrollments();
}
async function loadEnrollments(){
 const q=new URLSearchParams({limit:'100'});if($('enrollment-run').value)q.set('run_id',$('enrollment-run').value);
 try{
  const data=await api('/portal/api/admin/learning/enrollments?'+q);const body=$('enrollment-body');body.replaceChildren();
  for(const r of data.items){
   const tr=el('tr');const values=[r.name,r.program_title+(r.cohort_label?' / '+r.cohort_label:''),r.access_start+' ~ '+r.access_end,r.status,r.source];
   for(const v of values){const td=el('td',v);tr.append(td);}
   const td=el('td');if(r.status!=='CANCELLED'){const b=el('button','취소','cancel');b.type='button';b.addEventListener('click',async()=>{
    if(!confirm('이 수강권을 취소할까요?'))return;
    try{await post('/portal/api/admin/learning/enrollments/cancel',{request_id:requestId(),reason:'관리자 수강권 취소',enrollment_id:r.enrollment_id,version:r.version});await loadEnrollments();}
    catch(e){text('enrollment-status','취소하지 못했습니다: '+(e.detail||e.status||''));}
   });td.append(b);}tr.append(td);body.append(tr);
  }
  text('enrollment-status',data.items.length?'':'등록된 수강권이 없습니다.');
 }catch(e){text('enrollment-status','수강권을 불러오지 못했습니다.');}
}
function resetSessionForm(){
 const f=$('session-form');const run=f.elements.run_id.value;f.reset();f.elements.run_id.value=run;
 f.elements.session_id.value='';f.elements.version.value='';$('session-reset').hidden=true;text('session-save','회차 저장');
}
async function loadSessions(){
 const run=$('session-run').value;const box=$('session-list');box.replaceChildren();
 if(!run){text('session-status','기수를 선택하면 등록된 회차가 표시됩니다.');return;}
 try{
  const rows=await api('/portal/api/admin/learning/sessions?'+new URLSearchParams({run_id:run}));
  for(const r of rows){
   const item=el('div',undefined,'session-admin-item');const info=el('div');
   info.append(el('b',String(r.sequence_no)+'회 · '+r.title),el('span',[r.mentor_name,r.video_url?'영상 등록':'영상 없음',r.material_url?'자료 등록':'자료 없음'].filter(Boolean).join(' / ')));
   const edit=el('button','수정');edit.type='button';edit.addEventListener('click',()=>{
    const f=$('session-form');f.elements.session_id.value=r.session_id;f.elements.version.value=String(r.version);
    f.elements.run_id.value=r.run_id;f.elements.sequence_no.value=String(r.sequence_no);f.elements.sequence_no.disabled=true;
    f.elements.title.value=r.title;f.elements.mentor_name.value=r.mentor_name||'';
    f.elements.starts_at.value=r.starts_at?new Date(r.starts_at).toISOString().slice(0,16):'';
    f.elements.ends_at.value=r.ends_at?new Date(r.ends_at).toISOString().slice(0,16):'';
    f.elements.video_url.value=r.video_url||'';f.elements.material_url.value=r.material_url||'';
    $('session-reset').hidden=false;text('session-save','회차 수정 저장');f.elements.title.focus();
   });item.append(info,edit);box.append(item);
  }
  text('session-status',rows.length?'':'등록된 회차가 없습니다.');
 }catch(e){text('session-status','회차를 불러오지 못했습니다.');}
}

async function boot(){
 try{
  const me=await api('/portal/api/me');if(me.role!=='admin')throw Object.assign(new Error(),{status:403});
  $('gate-login').hidden=true;$('retry').hidden=true;$('gate').hidden=true;$('content').hidden=false;await loadCatalog();
 }catch(e){
  $('content').hidden=true;$('gate').hidden=false;
  if(e.status===401){
   text('gate-text','로그인이 필요합니다.');$('retry').hidden=true;$('gate-login').hidden=false;
   if(!state.loginPrompted){state.loginPrompted=true;setTimeout(()=>$('gate-login').click(),0);}
  }else{
   $('gate-login').hidden=true;text('gate-text',e.status===403?'관리자 권한이 필요합니다.':'연결 상태를 확인해 주세요.');$('retry').hidden=false;
  }
 }
}
$('retry').addEventListener('click',boot);$('refresh').addEventListener('click',loadCatalog);$('enrollment-run').addEventListener('change',loadEnrollments);$('session-run').addEventListener('change',()=>{resetSessionForm();loadSessions();});$('session-reset').addEventListener('click',()=>{const f=$('session-form');f.elements.sequence_no.disabled=false;resetSessionForm();loadSessions();});
$('program-form').addEventListener('submit',async e=>{
 e.preventDefault();const f=formData(e.currentTarget);
 const body={request_id:requestId(),reason:f.reason,program_id:f.program_id,title:f.title,description:f.description,
   access_mode:f.access_mode,fixed_months:f.access_mode==='fixed_months'?Number(f.fixed_months):null};
 try{await post('/portal/api/admin/learning/programs',body);e.currentTarget.reset();text('program-status','저장했습니다.');await loadCatalog();}
 catch(x){text('program-status','저장하지 못했습니다: '+(x.detail||x.status||''));}
});
$('run-form').addEventListener('submit',async e=>{
 e.preventDefault();const f=formData(e.currentTarget);
 const body={request_id:requestId(),reason:f.reason,program_id:f.program_id,cohort_label:f.cohort_label,
   starts_on:f.starts_on,ends_on:f.ends_on,default_access_start:f.default_access_start,default_access_end:f.default_access_end,
   recruit_opens_at:null,recruit_closes_at:null,capacity:f.capacity?Number(f.capacity):null,status:f.status,price_krw:Number(f.price_krw||0)};
 try{await post('/portal/api/admin/learning/runs',body);text('run-status','저장했습니다.');await loadCatalog();}
 catch(x){text('run-status','저장하지 못했습니다: '+(x.detail||x.status||''));}
});
$('target-search').addEventListener('click',async()=>{
 const q=$('target-q').value.trim();const box=$('target-results');box.replaceChildren();text('grant-status','검색 중입니다.');
 try{
  const rows=await api('/portal/api/admin/learning/targets?'+new URLSearchParams({q,limit:'20'}));
  for(const r of rows){const b=el('button',undefined,'target-item');b.type='button';b.append(el('b',r.name),el('span',[r.phone_masked,r.email_masked].filter(Boolean).join(' / ')||'연락처 없음'));b.addEventListener('click',()=>{
   state.selected=r;$('grant-form').elements.member_id.value=r.target_type==='member'?r.member_id:'';
   $('grant-form').elements.learner_id.value=r.target_type==='learner'?r.learner_id:'';
   $('selected-target').value=r.name;box.replaceChildren();text('grant-status','선택했습니다.');
  });box.append(b);}
  if(!rows.length)text('grant-status','검색 결과가 없습니다. 비회원 신규 등록은 기존 수강생 명단에서 먼저 생성해 주세요.');else text('grant-status','');
 }catch(x){text('grant-status','검색하지 못했습니다.');}
});
$('grant-form').addEventListener('submit',async e=>{
 e.preventDefault();const f=formData(e.currentTarget);if(!state.selected){text('grant-status','수강생을 먼저 선택해 주세요.');return;}
 const body={request_id:requestId(),reason:f.reason,run_id:f.run_id,member_id:f.member_id||null,learner_id:f.learner_id||null,profile:null,
   access_start:f.access_start,access_end:f.access_end,note:f.note};
 try{await post('/portal/api/admin/learning/enrollments',body);text('grant-status','수강권을 지급했습니다.');await loadCatalog();}
 catch(x){text('grant-status','지급하지 못했습니다: '+(x.detail||x.status||''));}
});
$('session-form').addEventListener('submit',async e=>{
 e.preventDefault();const form=e.currentTarget;form.elements.sequence_no.disabled=false;const f=formData(form);const editing=Boolean(f.session_id);
 const body=editing
  ?{request_id:requestId(),reason:f.reason,session_id:f.session_id,version:Number(f.version),title:f.title,mentor_name:f.mentor_name,
    starts_at:isoLocal(f.starts_at),ends_at:isoLocal(f.ends_at),video_url:f.video_url,material_url:f.material_url,cancelled:false}
  :{request_id:requestId(),reason:f.reason,run_id:f.run_id,sequence_no:Number(f.sequence_no),title:f.title,mentor_name:f.mentor_name,
    starts_at:isoLocal(f.starts_at),ends_at:isoLocal(f.ends_at),video_url:f.video_url,material_url:f.material_url};
 try{
  await post(editing?'/portal/api/admin/learning/sessions/update':'/portal/api/admin/learning/sessions',body);
  text('session-status',editing?'회차를 수정했습니다.':'회차를 저장했습니다.');resetSessionForm();form.elements.sequence_no.disabled=false;await loadSessions();
 }catch(x){if(editing)form.elements.sequence_no.disabled=true;text('session-status','저장하지 못했습니다: '+(x.detail||x.status||''));}
});
$('logout').addEventListener('click',async()=>{try{const t=await csrf();await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':t}});location.href='/';}catch{ text('action-status','로그아웃하지 못했습니다.');}});
boot();
})();
