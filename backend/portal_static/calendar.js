'use strict';
(()=>{
const $=id=>document.getElementById(id);
const PALETTE=[
  ['#3978F6','color-blue','재개발중급반'],
  ['#FF9F26','color-orange','리치온 인테리어'],
  ['#D8BD78','color-gold','무료 브리핑'],
  ['#FF5757','color-red','리치온 스터디'],
  ['#00B622','color-green','Pre리치온'],
  ['#C000DB','color-purple','스터디 전체'],
];
const COLOR=new Map(PALETTE.map(x=>[x[0],{cls:x[1],label:x[2]}]));
const state={month:null,items:[],selected:null,kind:'EVENT',bannerAnchor:null};
const requestId=()=>crypto.randomUUID();
const text=(id,v)=>{if($(id))$(id).textContent=String(v??'');};
const el=(tag,value,cls)=>{const x=document.createElement(tag);if(value!==undefined)x.textContent=String(value);if(cls)x.className=cls;return x;};
async function api(path,options={}){const r=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',...options});if(!r.ok){const e=new Error('request_failed');e.status=r.status;try{e.detail=(await r.json()).detail}catch{}throw e;}return r.status===204?null:r.json();}
async function csrf(){return (await api('/auth/csrf')).csrf_token;}
async function post(path,body){const token=await csrf();return api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(body)});}
function kstToday(){const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const o=Object.fromEntries(p.map(x=>[x.type,x.value]));return o.year+'-'+o.month+'-'+o.day;}
function kstMonth(){return kstToday().slice(0,7);}
function shiftMonth(value,delta){const [y,m]=value.split('-').map(Number);const d=new Date(Date.UTC(y,m-1+delta,1));return d.getUTCFullYear()+'-'+String(d.getUTCMonth()+1).padStart(2,'0');}
function isoDate(date){return date.toISOString().slice(0,10);}
function parseDate(value){const [y,m,d]=value.split('-').map(Number);return new Date(Date.UTC(y,m-1,d));}
function shiftDate(value,days){const d=parseDate(value);d.setUTCDate(d.getUTCDate()+days);return isoDate(d);}
function daysBetween(a,b){return Math.round((parseDate(b)-parseDate(a))/86400000);}
function colorMeta(hex){return COLOR.get(hex)||COLOR.get('#3978F6');}
function colorClass(hex){return colorMeta(hex).cls;}
function updateColor(){
  const hex=$('color-select').value,meta=colorMeta(hex);
  $('color-preview').className='color-preview '+meta.cls;
  text('color-caption','캘린더 범례: '+meta.label);
}
function setKind(kind,{fresh=false}={}){
  state.kind=kind;
  for(const button of document.querySelectorAll('[data-calendar-kind]'))button.setAttribute('aria-pressed',String(button.dataset.calendarKind===kind));
  for(const node of document.querySelectorAll('.banner-only'))node.hidden=kind!=='BANNER';
  for(const node of document.querySelectorAll('.event-only'))node.hidden=kind!=='EVENT';
  text('date-caption',kind==='BANNER'?'시작일':'날짜');
  text('course-caption',kind==='BANNER'?'문구':'과정');
  const course=$('calendar-form').elements.course_label;
  course.placeholder=kind==='BANNER'?'예: 추석연휴':'예: Pre리치온';
  if(kind==='BANNER'){
    const f=$('calendar-form').elements;
    if(!f.end_date.value)f.end_date.value=f.event_date.value;
    if(fresh){f.color_hex.value='#FF5757';updateColor();}
  }
}
function formValues(){
  const f=$('calendar-form').elements;
  return {display_kind:state.kind,event_date:f.event_date.value,end_date:state.kind==='BANNER'?(f.end_date.value||null):null,
          color_hex:f.color_hex.value,course_label:f.course_label.value.trim(),
          content_text:state.kind==='EVENT'?f.content_text.value.trim():''};
}
function valid(values){
  if(!values.event_date||!values.course_label){text('editor-status',state.kind==='BANNER'?'시작일 / 종료일 / 문구를 입력해 주세요.':'날짜 / 과정을 입력해 주세요.');return false;}
  if(values.display_kind==='BANNER'&&(!values.end_date||values.end_date<values.event_date)){text('editor-status','종료일은 시작일과 같거나 뒤여야 합니다.');return false;}
  return true;
}
function fallbackDate(){return state.month&&state.month!==kstMonth()?state.month+'-01':kstToday();}
function openDialog(){const d=$('calendar-editor');if(!d.open)d.showModal();}
function resetEditor(date){
  state.selected=null;state.bannerAnchor=null;$('calendar-form').reset();
  const f=$('calendar-form').elements;f.event_date.value=date||fallbackDate();f.color_hex.value='#3978F6';f.content_text.value='';
  setKind('EVENT',{fresh:true});updateColor();text('editor-title','일정 추가');
  $('copy-event').hidden=true;$('delete-event').hidden=true;text('editor-status','');openDialog();
}
function edit(item){
  state.selected=item;
  const f=$('calendar-form').elements;
  f.event_date.value=item.event_date;f.end_date.value=item.end_date||'';f.color_hex.value=item.color_hex;
  f.course_label.value=item.course_label;f.content_text.value=item.content_text||'';
  setKind(item.display_kind||'EVENT');updateColor();
  state.bannerAnchor=item.display_kind==='BANNER'?{start:item.event_date,end:item.end_date}:null;
  text('editor-title',item.display_kind==='BANNER'?'강조 문구 수정':'일정 수정');
  $('copy-event').hidden=false;$('delete-event').hidden=false;text('editor-status','');openDialog();
}
function eventButton(item){
  const b=el('button',undefined,'calendar-event-item');b.type='button';b.setAttribute('aria-label',item.course_label+(item.content_text?' / '+item.content_text:''));
  const line=el('span',undefined,'event-label-line'),dot=el('i',undefined,'event-dot '+colorClass(item.color_hex));
  line.append(dot,el('span',item.course_label,'event-course'));b.append(line);
  if(item.content_text)b.append(el('span',item.content_text,'event-content'));
  b.addEventListener('click',event=>{event.stopPropagation();edit(item);});return b;
}
function renderLegend(){
  const root=$('calendar-legend');root.replaceChildren();
  for(const [,cls,label] of PALETTE){const row=el('span',undefined,'calendar-legend-item');row.append(el('i',undefined,'calendar-legend-dot '+cls),document.createTextNode(label));root.append(row);}
}
function monthGrid(){
  const [y,m]=state.month.split('-').map(Number),first=new Date(Date.UTC(y,m-1,1)),firstDow=first.getUTCDay(),days=new Date(Date.UTC(y,m,0)).getUTCDate();
  const total=Math.max(35,Math.ceil((firstDow+days)/7)*7),start=new Date(Date.UTC(y,m-1,1-firstDow)),dates=[];
  for(let i=0;i<total;i++){const d=new Date(start);d.setUTCDate(start.getUTCDate()+i);dates.push(isoDate(d));}
  return dates;
}
function renderDesktop(){
  const dates=monthGrid(),events=state.items.filter(x=>x.display_kind!=='BANNER'),banners=state.items.filter(x=>x.display_kind==='BANNER'),by={};
  for(const item of events)(by[item.event_date]??=[]).push(item);
  const root=$('calendar-weeks');root.replaceChildren();
  for(let w=0;w<dates.length;w+=7){
    const weekDates=dates.slice(w,w+7),week=el('section',undefined,'calendar-week'),grid=el('div',undefined,'calendar-week-grid');
    weekDates.forEach((key,index)=>{
      const current=key.startsWith(state.month),items=by[key]||[],day=Number(key.slice(8)),cell=el('div',undefined,'calendar-day'+(current?'':' outside')+(index===0?' sunday':'')+(index===6?' saturday':'')+(items.length?' has-event':''));
      cell.dataset.date=key;cell.setAttribute('aria-label',key);
      const dateNode=el('div',day,'calendar-date'+(items.length?' '+colorClass(items[0].color_hex):''));
      cell.append(dateNode);
      if(current)cell.addEventListener('click',()=>resetEditor(key));
      for(const item of items)cell.append(eventButton(item));
      grid.append(cell);
    });
    week.append(grid);
    const bannerGrid=el('div',undefined,'calendar-banner-grid');
    let count=0;
    for(const item of banners){
      const rangeStart=item.event_date>weekDates[0]?item.event_date:weekDates[0];
      const itemEnd=item.end_date||item.event_date,rangeEnd=itemEnd<weekDates[6]?itemEnd:weekDates[6];
      if(rangeStart>rangeEnd)continue;
      const startIndex=weekDates.findIndex(x=>x===rangeStart),endIndex=weekDates.findIndex(x=>x===rangeEnd);
      if(startIndex<0||endIndex<startIndex)continue;
      const b=el('button',item.course_label,'calendar-banner '+colorClass(item.color_hex)+' start-'+(startIndex+1)+' span-'+(endIndex-startIndex+1));b.type='button';b.setAttribute('aria-label',item.course_label+' '+item.event_date+'부터 '+itemEnd+'까지');b.addEventListener('click',()=>edit(item));bannerGrid.append(b);count++;
    }
    if(count)week.append(bannerGrid);
    root.append(week);
  }
}
function renderMobile(){
  const root=$('calendar-mobile-list');root.replaceChildren();
  const banners=state.items.filter(x=>x.display_kind==='BANNER').sort((a,b)=>a.event_date.localeCompare(b.event_date));
  for(const item of banners){
    const label=(item.end_date&&item.end_date!==item.event_date?item.event_date.slice(5).replace('-','/')+'–'+item.end_date.slice(5).replace('-','/')+' ':'')+item.course_label;
    const b=el('button',label,'mobile-banner '+colorClass(item.color_hex));b.type='button';b.addEventListener('click',()=>edit(item));root.append(b);
  }
  const events=state.items.filter(x=>x.display_kind!=='BANNER'&&x.event_date.startsWith(state.month)),by={};
  for(const item of events)(by[item.event_date]??=[]).push(item);
  for(const key of Object.keys(by).sort()){
    const box=el('section',undefined,'mobile-day'),meta=el('div',undefined,'mobile-date has-event '+colorClass(by[key][0].color_hex));
    meta.textContent=String(Number(key.slice(8)));const body=el('div');
    for(const item of by[key]){
      const b=el('button',undefined,'mobile-event');b.type='button';const line=el('span',undefined,'event-label-line');line.append(el('i',undefined,'event-dot '+colorClass(item.color_hex)),el('span',item.course_label,'event-course'));b.append(line);if(item.content_text)b.append(el('span',item.content_text,'event-content'));b.addEventListener('click',()=>edit(item));body.append(b);
    }
    box.append(meta,body);root.append(box);
  }
}
function renderCalendar(){
  const [y,m]=state.month.split('-').map(Number);text('month-label',y+'년 '+m+'월');renderLegend();renderDesktop();renderMobile();
  text('calendar-status',state.items.length?'':'등록된 일정이 없습니다. 날짜를 눌러 첫 일정을 추가하세요.');
  const list=$('course-suggestions'),known=new Set(Array.from(list.options).map(x=>x.value));
  for(const item of state.items.filter(x=>x.display_kind!=='BANNER'))if(item.course_label&&!known.has(item.course_label)){const o=document.createElement('option');o.value=item.course_label;list.append(o);known.add(item.course_label);}
}
async function loadMonth(){text('calendar-status','불러오는 중입니다.');const data=await api('/portal/api/admin/learning/calendar?'+new URLSearchParams({month:state.month}));state.items=data.items;renderCalendar();}
async function selectCreated(result,date,{keepOpen=false}={}){
  state.month=date.slice(0,7);await loadMonth();const item=state.items.find(x=>x.event_id===result.event_id);
  if(item){if(keepOpen)edit(item);else state.selected=item;}else state.selected=null;
}
async function boot(){try{const me=await api('/portal/api/me');if(me.role!=='admin')throw Object.assign(new Error(),{status:403});$('gate').hidden=true;$('content').hidden=false;state.month=kstMonth();await loadMonth();}catch(e){text('gate-text',e.status===403?'관리자 권한이 필요합니다.':'로그인 또는 연결 상태를 확인해 주세요.');$('retry').hidden=false;}}
$('retry').addEventListener('click',boot);$('add-event').addEventListener('click',()=>resetEditor());$('close-editor').addEventListener('click',()=>$('calendar-editor').close());$('cancel-editor').addEventListener('click',()=>$('calendar-editor').close());
for(const button of document.querySelectorAll('[data-calendar-kind]'))button.addEventListener('click',()=>setKind(button.dataset.calendarKind,{fresh:!state.selected}));
$('color-select').addEventListener('change',updateColor);
$('calendar-form').elements.event_date.addEventListener('change',event=>{if(state.kind!=='BANNER'||!state.bannerAnchor)return;const f=$('calendar-form').elements,delta=daysBetween(state.bannerAnchor.start,event.target.value);f.end_date.value=shiftDate(state.bannerAnchor.end,delta);});
$('today').addEventListener('click',async()=>{state.month=kstMonth();await loadMonth();});$('prev-month').addEventListener('click',async()=>{state.month=shiftMonth(state.month,-1);await loadMonth();});$('next-month').addEventListener('click',async()=>{state.month=shiftMonth(state.month,1);await loadMonth();});
$('calendar-form').addEventListener('submit',async e=>{e.preventDefault();const values=formValues();if(!valid(values))return;const updating=!!state.selected,path=updating?'/portal/api/admin/learning/calendar-events/update':'/portal/api/admin/learning/calendar-events',body={request_id:requestId(),reason:updating?'캘린더 일정 수정':'캘린더 일정 등록',...values};if(updating)Object.assign(body,{event_id:state.selected.event_id,version:state.selected.version,deleted:false});try{await post(path,body);state.month=values.event_date.slice(0,7);await loadMonth();$('calendar-editor').close();text('calendar-status','저장했습니다.');}catch(x){text('editor-status','저장하지 못했습니다: '+(x.detail||x.status||''));}});
$('copy-event').addEventListener('click',async()=>{if(!state.selected)return;const values=formValues();if(!valid(values))return;try{const result=await post('/portal/api/admin/learning/calendar-events',{request_id:requestId(),reason:'캘린더 일정 복사',...values});text('editor-status','선택한 날짜에 복사했습니다.');await selectCreated(result,values.event_date,{keepOpen:true});}catch(x){text('editor-status','복사하지 못했습니다: '+(x.detail||x.status||''));}});
$('delete-event').addEventListener('click',async()=>{if(!state.selected||!confirm('이 항목을 삭제할까요?'))return;const item=state.selected;try{await post('/portal/api/admin/learning/calendar-events/update',{request_id:requestId(),reason:'캘린더 일정 삭제',event_id:item.event_id,version:item.version,display_kind:item.display_kind,event_date:item.event_date,end_date:item.end_date||null,color_hex:item.color_hex,course_label:item.course_label,content_text:item.content_text||'',deleted:true});state.month=(item.event_date||state.month).slice(0,7);await loadMonth();$('calendar-editor').close();text('calendar-status','삭제했습니다.');}catch(x){text('editor-status','삭제하지 못했습니다: '+(x.detail||x.status||''));}});
$('logout').addEventListener('click',async()=>{try{const t=await csrf();await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':t}});location.href='/';}catch{text('action-status','로그아웃하지 못했습니다.');}});
boot();
})();
