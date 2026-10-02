'use strict';
(()=>{
const {$,text,el,requestId,api,csrf,post}=window.RichonOps;
const state={programs:[],runs:[],selected:null,sessionEditing:null,sessions:[],adjusting:null};
const date=v=>v||'—';
const money=v=>new Intl.NumberFormat('ko-KR').format(v||0)+'원';
const dateTime=v=>v?new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:'Asia/Seoul'}).format(new Date(v)):'—';
function isoLocal(value){
 if(!value)return '';
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));
 const o=Object.fromEntries(parts.map(x=>[x.type,x.value]));
 return o.year+'-'+o.month+'-'+o.day+'T'+o.hour+':'+o.minute;
}
const seoulIso=value=>value?value+':00+09:00':null;
const safeHttps=value=>typeof value==='string'&&value.startsWith('https://')?value:null;
function formData(form){
 const d=Object.fromEntries(new FormData(form));
 for(const k of Object.keys(d))if(d[k]==='')d[k]=null;
 return d;
}
function fillSelect(select,items,label,selectFirst=false){
 const current=select.value;
 select.replaceChildren();
 const blank=el('option',label);blank.value='';select.append(blank);
 for(const item of items){const o=el('option',item.label);o.value=item.value;select.append(o);}
 if(current&&items.some(x=>x.value===current))select.value=current;
 else if(selectFirst&&items.length)select.value=items[0].value;
}
function catalogOptions(){
 const ps=state.programs.filter(x=>!x.archived).map(x=>({value:x.program_id,label:x.title}));
 fillSelect($('run-program'),ps,'프로그램 선택');
 const rs=state.runs.filter(x=>!x.archived).map(x=>({value:x.run_id,label:x.program_title+(x.cohort_label?' / '+x.cohort_label:'')}));
 fillSelect($('grant-run'),rs,'기수 선택');
 fillSelect($('enrollment-run'),rs,'전체 기수');
 fillSelect($('session-run'),rs,'기수 선택',true);
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
function resetSessionForm(){
 state.sessionEditing=null;const form=$('session-form');form.reset();
 form.elements.sequence_no.disabled=false;
 $('session-save').textContent='회차 추가';$('session-cancel-edit').hidden=true;
 text('session-status','');
}
function editSession(row){
 state.sessionEditing=row;const form=$('session-form');
 form.elements.sequence_no.value=String(row.sequence_no);form.elements.sequence_no.disabled=true;
 form.elements.title.value=row.title||'';form.elements.mentor_name.value=row.mentor_name||'';
 form.elements.starts_at.value=isoLocal(row.starts_at);form.elements.ends_at.value=isoLocal(row.ends_at);
 form.elements.video_url.value=row.video_url||row.content_url||'';form.elements.material_url.value=row.material_url||'';
 form.elements.reason.value='강의 회차 수정';
 $('session-save').textContent='수정 저장';$('session-cancel-edit').hidden=false;
 form.elements.title.focus();
}
function sessionUpdateBody(row,cancelled,reason){
 return {request_id:requestId(),reason,session_id:row.session_id,version:row.version,
  title:row.title,mentor_name:row.mentor_name,starts_at:row.starts_at,ends_at:row.ends_at,
  video_url:row.video_url,material_url:row.material_url,cancelled};
}
function sessionLink(label,url){
 const value=safeHttps(url);if(!value)return el('span',label+' 없음','session-resource empty');
 const a=el('a',label+' 보기','session-resource');a.href=value;a.target='_blank';a.rel='noopener noreferrer';return a;
}
function renderSessions(){
 const root=$('session-list');root.replaceChildren();
 if(!state.sessions.length){root.append(el('div','등록된 회차가 없습니다.','session-empty'));return;}
 for(const row of state.sessions){
  const card=el('article',undefined,'session-card'+(row.cancelled?' is-cancelled':''));
  const top=el('div',undefined,'session-card-head'),title=el('div');
  title.append(el('strong',row.sequence_no+'회 · '+row.title),el('span',row.cancelled?'사용 중지됨':dateTime(row.starts_at),'session-meta'));
  const badge=el('span',row.cancelled?'중지':'사용 중',row.cancelled?'session-state stopped':'session-state');
  top.append(title,badge);
  const meta=el('div',undefined,'session-meta-line');
  if(row.mentor_name)meta.append(el('span','멘토 '+row.mentor_name));
  if(row.ends_at)meta.append(el('span','종료 '+dateTime(row.ends_at)));
  const resources=el('div',undefined,'session-resources');
  resources.append(sessionLink('영상',row.video_url||row.content_url),sessionLink('자료',row.material_url));
  const actions=el('div',undefined,'session-actions');
  const edit=el('button','수정');edit.type='button';edit.addEventListener('click',()=>editSession(row));
  const toggle=el('button',row.cancelled?'복구':'사용 중지',row.cancelled?'restore':'cancel');toggle.type='button';
  toggle.addEventListener('click',async()=>{
   if(!row.cancelled&&!confirm('이 회차를 사용 중지할까요? 수강생 화면에서 숨겨집니다.'))return;
   toggle.disabled=true;
   try{
    await post('/portal/api/admin/learning/sessions/update',sessionUpdateBody(
      row,!row.cancelled,row.cancelled?'관리자 회차 복구':'관리자 회차 사용 중지'));
    const message=row.cancelled?'회차를 복구했습니다.':'회차를 사용 중지했습니다.';
    await loadSessions();text('session-status',message);
   }catch(e){text('session-status','변경하지 못했습니다: '+(e.detail||e.status||''));}
   finally{toggle.disabled=false;}
  });
  actions.append(edit,toggle);card.append(top,meta,resources,actions);root.append(card);
 }
}
async function loadSessions(){
 const runId=$('session-run').value;state.sessions=[];state.sessionEditing=null;$('session-list').replaceChildren();
 if(!runId){resetSessionForm();text('session-status','기수를 선택해 주세요.');return;}
 text('session-status','회차를 불러오는 중입니다.');
 try{
  const rows=await api('/portal/api/admin/learning/sessions?'+new URLSearchParams({run_id:runId,include_cancelled:'true'}));
  state.sessions=Array.isArray(rows)?rows:[];resetSessionForm();renderSessions();
  text('session-status',state.sessions.length?'':'등록된 회차가 없습니다.');
 }catch(e){text('session-status','회차를 불러오지 못했습니다.');}
}
async function loadCatalog(){
 text('catalog-status','불러오는 중입니다.');
 const [p,r]=await Promise.all([api('/portal/api/admin/learning/programs'),api('/portal/api/admin/learning/runs')]);
 state.programs=p.items;state.runs=r.items;renderCatalog();catalogOptions();text('catalog-status','');await Promise.all([loadEnrollments(),loadSessions()]);
}
function seoulDate(){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
 const o=Object.fromEntries(parts.map(x=>[x.type,x.value]));return o.year+'-'+o.month+'-'+o.day;
}
function visible(id,show){$(id).hidden=!show;}
function adjustmentLabel(kind){
 return {SUSPEND:'휴식',RESUME:'재개',EXTEND:'연장',REFUND:'환불'}[kind]||kind;
}
function syncRefundFields(){
 const form=$('adjust-form'),partial=form.elements.refund_kind.value==='PARTIAL';
 visible('adjust-end-wrap',partial);
 form.elements.new_access_end.required=partial;
 if(!partial)form.elements.new_access_end.value='';
}
function openAdjustment(row,operation){
 state.adjusting=row;const form=$('adjust-form');form.reset();
 form.elements.operation.value=operation;form.elements.enrollment_id.value=row.enrollment_id;
 form.elements.version.value=String(row.version);form.elements.effective_on.value=seoulDate();
 for(const id of ['adjust-end-wrap','adjust-extension-wrap','adjust-refund-kind-wrap','adjust-refund-amount-wrap','adjust-refund-ref-wrap'])visible(id,false);
 form.elements.new_access_end.required=false;form.elements.extension_kind.required=false;
 let title='',hint='',reason='';
 if(operation==='suspend'){
  title='수강 휴식';reason='관리자 수강 일시정지';
  hint='현재 종료일 '+row.access_end+'은 그대로 유지합니다. 재개할 때 필요한 경우 연장할 수 있습니다.';
 }else if(operation==='resume'){
  title='수강 재개';reason='관리자 수강 재개';visible('adjust-end-wrap',true);visible('adjust-extension-wrap',true);
  hint='기간 연장이 없으면 새 종료일을 비워두세요. 연장할 경우 새 종료일과 무료/유료 구분을 함께 선택합니다.';
 }else if(operation==='extend'){
  title='수강기간 연장';reason='관리자 수강기간 연장';visible('adjust-end-wrap',true);visible('adjust-extension-wrap',true);
  form.elements.new_access_end.required=true;form.elements.extension_kind.required=true;
  hint='현재 종료일 '+row.access_end+'보다 뒤 날짜만 입력할 수 있습니다.';
 }else if(operation==='refund'){
  title='수강권 환불 기록';reason='관리자 환불 처리';visible('adjust-refund-kind-wrap',true);
  visible('adjust-refund-amount-wrap',true);visible('adjust-refund-ref-wrap',true);
  hint='이 화면은 환불 사실을 기록하는 기능이며 PG 환불을 실행하거나 검증하지 않습니다.';
  syncRefundFields();
 }
 form.elements.reason.value=reason;
 $('adjust-title').textContent=title;
 $('adjust-summary').textContent=row.name+' / '+row.program_title+(row.cohort_label?' / '+row.cohort_label:'')+' / '+row.access_start+' ~ '+row.access_end;
 $('adjust-hint').textContent=hint;
 $('adjust-dialog').showModal();
}
async function showAdjustmentHistory(row){
 const dialog=$('adjust-history-dialog'),root=$('adjust-history-list');root.replaceChildren();
 $('adjust-history-summary').textContent=row.name+' / '+row.program_title+(row.cohort_label?' / '+row.cohort_label:'');
 text('adjust-history-status','불러오는 중입니다.');dialog.showModal();
 try{
  const rows=await api('/portal/api/admin/learning/enrollments/'+row.enrollment_id+'/adjustments?limit=100');
  for(const x of rows){
   const card=el('article',undefined,'adjust-history-item');
   card.append(el('strong',adjustmentLabel(x.kind)+' / '+x.effective_on));
   card.append(el('span',x.status_before+' → '+x.status_after));
   card.append(el('span',x.access_start_before+' ~ '+x.access_end_before+' → '+x.access_start_after+' ~ '+x.access_end_after));
   if(x.extension_kind)card.append(el('span','연장: '+(x.extension_kind==='FREE'?'무료':'유료')));
   if(x.refund_kind){
    const detail='환불: '+(x.refund_kind==='FULL'?'전액':'부분')+(x.refund_amount_krw!=null?' / '+money(x.refund_amount_krw):'');
    card.append(el('span',detail,'refund-line'));
   }
   if(x.refund_reference)card.append(el('span','참조: '+x.refund_reference));
   card.append(el('span','사유: '+x.note));
   root.append(card);
  }
  text('adjust-history-status',rows.length?'':'변경 이력이 없습니다.');
 }catch(e){text('adjust-history-status','이력을 불러오지 못했습니다.');}
}
function actionButton(label,className,handler){
 const b=el('button',label,className);b.type='button';b.addEventListener('click',handler);return b;
}
async function cancelEnrollment(row){
 if(!confirm('이 수강권을 취소할까요? 환불 기록이 필요한 경우에는 환불 기능을 사용하세요.'))return;
 try{
  await post('/portal/api/admin/learning/enrollments/cancel',{
   request_id:requestId(),reason:'관리자 수강권 취소',enrollment_id:row.enrollment_id,version:row.version});
  await loadEnrollments();text('enrollment-status','수강권을 취소했습니다.');
 }catch(e){text('enrollment-status','취소하지 못했습니다: '+(e.detail||e.status||''));}
}
async function restoreEnrollment(row){
 if(!confirm('취소한 수강권을 복구할까요?'))return;
 try{
  await post('/portal/api/admin/learning/enrollments/restore',{
   request_id:requestId(),reason:'관리자 수강권 복구',enrollment_id:row.enrollment_id,version:row.version});
  await loadEnrollments();text('enrollment-status','수강권을 복구했습니다.');
 }catch(e){text('enrollment-status','복구하지 못했습니다: '+(e.detail||e.status||''));}
}
async function loadEnrollments(){
 const q=new URLSearchParams({limit:'100'});if($('enrollment-run').value)q.set('run_id',$('enrollment-run').value);
 try{
  const data=await api('/portal/api/admin/learning/enrollments?'+q);const body=$('enrollment-body');body.replaceChildren();
  for(const r of data.items){
   const tr=el('tr');const values=[r.name,r.program_title+(r.cohort_label?' / '+r.cohort_label:''),r.access_start+' ~ '+r.access_end,r.status,r.source];
   for(const v of values){const td=el('td',v);tr.append(td);}
   const td=el('td');td.className='enrollment-actions';
   if(r.status==='CANCELLED'){
    td.append(actionButton('복구','restore',()=>restoreEnrollment(r)));
   }else{
    if(r.status==='SCHEDULED'||r.status==='ACTIVE')td.append(actionButton('휴식','suspend',()=>openAdjustment(r,'suspend')));
    if(r.status==='SUSPENDED')td.append(actionButton('재개','restore',()=>openAdjustment(r,'resume')));
    td.append(actionButton('연장','extend',()=>openAdjustment(r,'extend')));
    td.append(actionButton('환불','refund',()=>openAdjustment(r,'refund')));
    td.append(actionButton('취소','cancel',()=>cancelEnrollment(r)));
   }
   td.append(actionButton('이력','history',()=>showAdjustmentHistory(r)));
   tr.append(td);body.append(tr);
  }
  text('enrollment-status',data.items.length?'':'등록된 수강권이 없습니다.');
 }catch(e){text('enrollment-status','수강권을 불러오지 못했습니다.');}
}
async function boot(){
 try{
  const me=await api('/portal/api/me');if(me.role!=='admin')throw Object.assign(new Error(),{status:403});
  $('gate').hidden=true;$('content').hidden=false;await loadCatalog();
 }catch(e){text('gate-text',e.status===403?'관리자 권한이 필요합니다.':'로그인 또는 연결 상태를 확인해 주세요.');$('retry').hidden=false;}
}
$('retry').addEventListener('click',boot);$('refresh').addEventListener('click',loadCatalog);$('enrollment-run').addEventListener('change',loadEnrollments);
$('session-run').addEventListener('change',()=>{resetSessionForm();loadSessions();});
$('session-cancel-edit').addEventListener('click',resetSessionForm);
$('session-form').addEventListener('submit',async e=>{
 e.preventDefault();const form=e.currentTarget,f=formData(form),runId=$('session-run').value;
 if(!runId){text('session-status','기수를 먼저 선택해 주세요.');return;}
 const editing=state.sessionEditing;
 const body=editing
  ?{request_id:requestId(),reason:f.reason,session_id:editing.session_id,version:editing.version,
    title:f.title,mentor_name:f.mentor_name,starts_at:seoulIso(f.starts_at),ends_at:seoulIso(f.ends_at),
    video_url:f.video_url,material_url:f.material_url,cancelled:editing.cancelled}
  :{request_id:requestId(),reason:f.reason,run_id:runId,sequence_no:Number(f.sequence_no),title:f.title,
    mentor_name:f.mentor_name,starts_at:seoulIso(f.starts_at),ends_at:seoulIso(f.ends_at),
    video_url:f.video_url,material_url:f.material_url};
 $('session-save').disabled=true;
 try{
  await post(editing?'/portal/api/admin/learning/sessions/update':'/portal/api/admin/learning/sessions',body);
  const message=editing?'회차를 수정했습니다.':'회차를 추가했습니다.';
  await loadSessions();text('session-status',message);
 }catch(x){text('session-status','저장하지 못했습니다: '+(x.detail||x.status||''));}
 finally{$('session-save').disabled=false;}
});
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
$('adjust-close').addEventListener('click',()=>$('adjust-dialog').close());
$('adjust-cancel').addEventListener('click',()=>$('adjust-dialog').close());
$('adjust-history-close').addEventListener('click',()=>$('adjust-history-dialog').close());
$('adjust-form').elements.refund_kind.addEventListener('change',syncRefundFields);
$('adjust-form').addEventListener('submit',async e=>{
 e.preventDefault();const form=e.currentTarget,f=formData(form),op=f.operation,row=state.adjusting;
 if(!row)return;
 const body={request_id:requestId(),reason:f.reason,enrollment_id:f.enrollment_id,
   version:Number(f.version),effective_on:f.effective_on};
 if(op==='resume'){
  body.new_access_end=f.new_access_end||null;body.extension_kind=f.extension_kind||null;
  if(Boolean(body.new_access_end)!==Boolean(body.extension_kind)){
   $('adjust-hint').textContent='종료일을 연장할 때는 무료/유료 구분도 함께 선택해 주세요.';return;
  }
 }else if(op==='extend'){
  body.new_access_end=f.new_access_end;body.extension_kind=f.extension_kind;
 }else if(op==='refund'){
  body.refund_kind=f.refund_kind;
  body.refund_amount_krw=f.refund_amount_krw==null?null:Number(f.refund_amount_krw);
  body.refund_reference=f.refund_reference||null;
  body.new_access_end=f.refund_kind==='PARTIAL'?f.new_access_end:null;
 }
 $('adjust-save').disabled=true;
 try{
  await post('/portal/api/admin/learning/enrollments/'+op,body);
  $('adjust-dialog').close();state.adjusting=null;await loadEnrollments();
  text('enrollment-status',{suspend:'수강을 휴식 처리했습니다.',resume:'수강을 재개했습니다.',extend:'수강기간을 연장했습니다.',refund:'환불 기록을 반영했습니다.'}[op]);
 }catch(x){$('adjust-hint').textContent='저장하지 못했습니다: '+(x.detail||x.status||'');}
 finally{$('adjust-save').disabled=false;}
});
$('logout').addEventListener('click',async()=>{try{const t=await csrf();await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':t}});location.href='/';}catch{ text('action-status','로그아웃하지 못했습니다.');}});
boot();
})();
