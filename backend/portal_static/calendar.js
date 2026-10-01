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
const state={month:null,items:[],selected:null,kind:'EVENT',bannerAnchor:null,pngResetTimer:null};
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
function holidaySegment(item,weekDates){
  const itemEnd=item.end_date||item.event_date;
  const rangeStart=item.event_date>weekDates[0]?item.event_date:weekDates[0];
  const rangeEnd=itemEnd<weekDates[6]?itemEnd:weekDates[6];
  if(rangeStart>rangeEnd)return null;
  const startIndex=weekDates.indexOf(rangeStart),endIndex=weekDates.indexOf(rangeEnd);
  if(startIndex<0||endIndex<startIndex)return null;
  return {startIndex,endIndex,count:endIndex-startIndex+1};
}
function bannerPlacement(item,dates){
  let best=null;
  for(let offset=0;offset<dates.length;offset+=7){
    const segment=holidaySegment(item,dates.slice(offset,offset+7));
    if(!segment)continue;
    const currentCount=dates.slice(offset+segment.startIndex,offset+segment.endIndex+1).filter(key=>key.startsWith(state.month)).length;
    if(!currentCount)continue;
    if(!best||currentCount>best.currentCount)best={weekIndex:offset/7,...segment,currentCount};
  }
  return best;
}
function bannerForDate(key,banners){
  return banners.find(item=>key>=item.event_date&&key<=(item.end_date||item.event_date))||null;
}
function renderDesktop(){
  const dates=monthGrid(),events=state.items.filter(x=>x.display_kind!=='BANNER'),banners=state.items.filter(x=>x.display_kind==='BANNER'),by={};
  for(const item of events)(by[item.event_date]??=[]).push(item);
  const placements=new Map(banners.map(item=>[item.event_id,bannerPlacement(item,dates)]));
  const root=$('calendar-weeks');root.replaceChildren();
  for(let w=0;w<dates.length;w+=7){
    const weekIndex=w/7,weekDates=dates.slice(w,w+7),week=el('section',undefined,'calendar-week'),grid=el('div',undefined,'calendar-week-grid');
    weekDates.forEach((key,index)=>{
      const current=key.startsWith(state.month),items=by[key]||[],holiday=bannerForDate(key,banners),day=Number(key.slice(8));
      let holidayEdge='';
      if(holiday){
        const previous=index>0?bannerForDate(weekDates[index-1],banners):null;
        const next=index<6?bannerForDate(weekDates[index+1],banners):null;
        const left=previous&&previous.event_id===holiday.event_id,right=next&&next.event_id===holiday.event_id;
        holidayEdge=left?(right?' holiday-middle':' holiday-end'):(right?' holiday-start':' holiday-single');
      }
      const classes='calendar-day'+(current?'':' outside')+(index===0?' sunday':'')+(index===6?' saturday':'')+(items.length?' has-event':'')+(holiday?' holiday-day '+colorClass(holiday.color_hex)+holidayEdge:'');
      const cell=el('div',undefined,classes);cell.dataset.date=key;cell.setAttribute('aria-label',key);
      const dateNode=el('div',day,'calendar-date'+(items.length?' '+colorClass(items[0].color_hex):''));
      cell.append(dateNode);
      if(current)cell.addEventListener('click',()=>resetEditor(key));
      for(const item of items)cell.append(eventButton(item));
      if(holiday){
        const placement=placements.get(holiday.event_id);
        if(placement&&placement.weekIndex===weekIndex&&placement.startIndex===index){
          cell.classList.add('holiday-label-host');
          const itemEnd=holiday.end_date||holiday.event_date;
          const label=el('button',holiday.course_label,'calendar-banner '+colorClass(holiday.color_hex));label.type='button';
          label.style.setProperty('--holiday-span',String(placement.count));
          label.style.width='calc('+(placement.count*100)+'% - 16px)';
          label.setAttribute('aria-label',holiday.course_label+' '+holiday.event_date+'부터 '+itemEnd+'까지');
          label.addEventListener('click',event=>{event.stopPropagation();edit(holiday);});cell.append(label);
        }
      }
      grid.append(cell);
    });
    week.append(grid);root.append(week);
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
function hexRgba(hex,alpha){
  const value=String(hex).replace('#','');const n=parseInt(value,16);
  return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+alpha+')';
}
function roundRectPath(ctx,x,y,w,h,r){
  const radius=Math.min(r,w/2,h/2);ctx.beginPath();ctx.moveTo(x+radius,y);ctx.arcTo(x+w,y,x+w,y+h,radius);ctx.arcTo(x+w,y+h,x,y+h,radius);ctx.arcTo(x,y+h,x,y,radius);ctx.arcTo(x,y,x+w,y,radius);ctx.closePath();
}
function fillRound(ctx,x,y,w,h,r,fill,stroke){
  roundRectPath(ctx,x,y,w,h,r);if(fill){ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1.2;ctx.stroke();}
}
function fitCanvasLines(ctx,value,maxWidth,maxLines){
  const chars=Array.from(String(value||''));const lines=[];let line='';
  for(const ch of chars){
    const next=line+ch;
    if(line&&ctx.measureText(next).width>maxWidth){lines.push(line);line=ch;if(lines.length===maxLines)break;}else line=next;
  }
  if(lines.length<maxLines&&line)lines.push(line);
  if(lines.length===maxLines){
    const used=lines.join('').length;
    if(chars.length>used){let last=lines[maxLines-1];while(last&&ctx.measureText(last+'…').width>maxWidth)last=last.slice(0,-1);lines[maxLines-1]=last+'…';}
  }
  return lines;
}
function drawCalendarSymbol(ctx,cx,top){
  ctx.fillStyle='#06163e';ctx.beginPath();ctx.moveTo(cx-34,top+29);ctx.lineTo(cx+22,top);ctx.lineTo(cx+22,top+57);ctx.lineTo(cx-8,top+78);ctx.lineTo(cx-8,top+39);ctx.lineTo(cx-34,top+57);ctx.closePath();ctx.fill();
  ctx.fillStyle='#D8BD78';ctx.beginPath();ctx.moveTo(cx-1,top+29);ctx.lineTo(cx+36,top+48);ctx.lineTo(cx+36,top+76);ctx.lineTo(cx-1,top+94);ctx.closePath();ctx.fill();
}
function drawCalendarPng(){
  const canvas=document.createElement('canvas');canvas.width=1200;canvas.height=1200;const ctx=canvas.getContext('2d');
  ctx.fillStyle='#fff';ctx.fillRect(0,0,1200,1200);ctx.textBaseline='middle';ctx.font='16px Pretendard, Arial, sans-serif';
  const [year,month]=state.month.split('-').map(Number);
  drawCalendarSymbol(ctx,510,34);
  ctx.fillStyle='#111';ctx.textAlign='center';ctx.font='800 38px Pretendard, Arial, sans-serif';ctx.fillText(year+'년 '+month+'월',510,158);ctx.fillText('리치온 캘린더',510,203);
  ctx.textAlign='left';ctx.font='600 17px Pretendard, Arial, sans-serif';
  PALETTE.forEach((item,index)=>{const y=58+index*29;ctx.fillStyle=item[0];ctx.beginPath();ctx.arc(850,y,5,0,Math.PI*2);ctx.fill();ctx.fillStyle='#222';ctx.fillText(item[2],865,y);});
  const dates=monthGrid(),rows=dates.length/7,x0=90,gridWidth=1020,colW=gridWidth/7,gridTop=322,gridBottom=1122,rowH=(gridBottom-gridTop)/rows;
  const weekdays=['Su','Mo','Tu','We','Th','Fr','Sa'];ctx.textAlign='center';ctx.font='500 22px Pretendard, Arial, sans-serif';
  weekdays.forEach((name,index)=>{ctx.fillStyle=index===0?'#ff5257':index===6?'#178de5':'#b9b9b9';ctx.fillText(name,x0+colW*(index+.5),285);});
  const events=state.items.filter(x=>x.display_kind!=='BANNER'),banners=state.items.filter(x=>x.display_kind==='BANNER'),by={};
  for(const item of events)(by[item.event_date]??=[]).push(item);
  const placements=new Map(banners.map(item=>[item.event_id,bannerPlacement(item,dates)]));
  for(let row=0;row<rows;row++){
    const rowY=gridTop+row*rowH,weekDates=dates.slice(row*7,row*7+7);
    if(row){ctx.save();ctx.strokeStyle='#c7c7c7';ctx.lineWidth=2;ctx.setLineDash([5,6]);ctx.beginPath();ctx.moveTo(x0,rowY);ctx.lineTo(x0+gridWidth,rowY);ctx.stroke();ctx.restore();}
    for(const item of banners){
      const segment=holidaySegment(item,weekDates);if(!segment)continue;
      const segmentKeys=weekDates.slice(segment.startIndex,segment.endIndex+1),currentKeys=segmentKeys.filter(key=>key.startsWith(state.month));
      if(!currentKeys.length)continue;
      const firstIndex=weekDates.indexOf(currentKeys[0]),lastIndex=weekDates.indexOf(currentKeys[currentKeys.length-1]);
      const segmentX=x0+firstIndex*colW+5,segmentW=(lastIndex-firstIndex+1)*colW-10;
      fillRound(ctx,segmentX,rowY+5,segmentW,rowH-10,13,hexRgba(item.color_hex,.055),null);
    }
    for(let col=0;col<7;col++){
      const key=weekDates[col],current=key.startsWith(state.month),items=by[key]||[],holiday=bannerForDate(key,banners),cx=x0+colW*(col+.5),cellX=x0+colW*col;
      const dateY=rowY+34,day=Number(key.slice(8));
      if(items.length){fillRound(ctx,cx-25,dateY-25,50,50,10,items[0].color_hex,null);ctx.fillStyle='#fff';ctx.font='650 25px Pretendard, Arial, sans-serif';}
      else if(holiday&&current){fillRound(ctx,cx-25,dateY-25,50,50,10,hexRgba(holiday.color_hex,.12),null);ctx.fillStyle=holiday.color_hex;ctx.font='700 23px Pretendard, Arial, sans-serif';}
      else{ctx.fillStyle=col===0?'#ff5257':col===6?'#178de5':'#b7b7b7';ctx.globalAlpha=current?1:.5;ctx.font='500 23px Pretendard, Arial, sans-serif';}
      ctx.textAlign='center';ctx.fillText(String(day),cx,dateY);ctx.globalAlpha=1;
      let eventY=rowY+72;
      for(const item of items.slice(0,2)){
        ctx.textAlign='left';ctx.fillStyle=item.color_hex;ctx.beginPath();ctx.arc(cellX+10,eventY,4,0,Math.PI*2);ctx.fill();
        ctx.fillStyle='#181818';ctx.font='700 14px Pretendard, Arial, sans-serif';const course=fitCanvasLines(ctx,item.course_label,colW-29,1)[0]||'';ctx.fillText(course,cellX+20,eventY);
        if(item.content_text){ctx.fillStyle='#454545';ctx.font='400 13px Pretendard, Arial, sans-serif';const lines=fitCanvasLines(ctx,item.content_text,colW-27,2);lines.forEach((line,i)=>ctx.fillText(line,cellX+20,eventY+18+i*16));eventY+=18+lines.length*16;}else eventY+=28;
      }
    }
    for(const item of banners){
      const placement=placements.get(item.event_id);if(!placement||placement.weekIndex!==row)continue;
      const labelX=x0+placement.startIndex*colW+8,labelW=placement.count*colW-16,labelY=rowY+rowH-34;
      fillRound(ctx,labelX,labelY,labelW,26,13,hexRgba(item.color_hex,.11),hexRgba(item.color_hex,.32));
      ctx.fillStyle=item.color_hex;ctx.textAlign='center';ctx.font='800 15px Pretendard, Arial, sans-serif';const label=fitCanvasLines(ctx,item.course_label,labelW-20,1)[0]||'';ctx.fillText(label,labelX+labelW/2,labelY+13);
    }
  }
  return canvas;
}
function canvasBlob(canvas){
  return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('png_blob_failed')),'image/png'));
}
function savePng(blob){
  const href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download=state.month+'-richon-calendar.png';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(href),1000);
}
async function copyCalendarPng(){
  const button=$('copy-png');if(state.pngResetTimer){clearTimeout(state.pngResetTimer);state.pngResetTimer=null;}
  button.disabled=true;button.classList.remove('is-success','is-error');button.textContent='PNG 생성 중';text('action-status','');
  let finalLabel='PNG 복사',finalClass='';
  try{
    const blob=await canvasBlob(drawCalendarPng());let copied=false;
    if(navigator.clipboard&&navigator.clipboard.write&&window.ClipboardItem){
      try{await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);copied=true;}catch{}
    }
    if(copied){
      finalLabel='✓ 복사 완료';finalClass='is-success';text('action-status','1200×1200 PNG 이미지를 클립보드에 복사했습니다.');
    }else{
      savePng(blob);finalLabel='✓ PNG 저장';finalClass='is-success';text('action-status','이미지 클립보드를 지원하지 않아 1200×1200 PNG 파일로 저장했습니다.');
    }
  }catch{
    finalLabel='복사 실패';finalClass='is-error';text('action-status','PNG 이미지를 만들지 못했습니다.');
  }
  button.disabled=false;button.textContent=finalLabel;if(finalClass)button.classList.add(finalClass);
  state.pngResetTimer=setTimeout(()=>{button.classList.remove('is-success','is-error');button.textContent='PNG 복사';state.pngResetTimer=null;},2200);
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
$('retry').addEventListener('click',boot);$('copy-png').addEventListener('click',copyCalendarPng);$('add-event').addEventListener('click',()=>resetEditor());$('close-editor').addEventListener('click',()=>$('calendar-editor').close());$('cancel-editor').addEventListener('click',()=>$('calendar-editor').close());
for(const button of document.querySelectorAll('[data-calendar-kind]'))button.addEventListener('click',()=>setKind(button.dataset.calendarKind,{fresh:!state.selected}));
$('color-select').addEventListener('change',updateColor);
$('calendar-form').elements.event_date.addEventListener('change',event=>{if(state.kind!=='BANNER'||!state.bannerAnchor)return;const f=$('calendar-form').elements,delta=daysBetween(state.bannerAnchor.start,event.target.value);f.end_date.value=shiftDate(state.bannerAnchor.end,delta);});
$('today').addEventListener('click',async()=>{state.month=kstMonth();await loadMonth();});$('prev-month').addEventListener('click',async()=>{state.month=shiftMonth(state.month,-1);await loadMonth();});$('next-month').addEventListener('click',async()=>{state.month=shiftMonth(state.month,1);await loadMonth();});
$('calendar-form').addEventListener('submit',async e=>{e.preventDefault();const values=formValues();if(!valid(values))return;const updating=!!state.selected,path=updating?'/portal/api/admin/learning/calendar-events/update':'/portal/api/admin/learning/calendar-events',body={request_id:requestId(),reason:updating?'캘린더 일정 수정':'캘린더 일정 등록',...values};if(updating)Object.assign(body,{event_id:state.selected.event_id,version:state.selected.version,deleted:false});try{await post(path,body);state.month=values.event_date.slice(0,7);await loadMonth();$('calendar-editor').close();text('calendar-status','저장했습니다.');}catch(x){text('editor-status','저장하지 못했습니다: '+(x.detail||x.status||''));}});
$('copy-event').addEventListener('click',async()=>{if(!state.selected)return;const values=formValues();if(!valid(values))return;try{const result=await post('/portal/api/admin/learning/calendar-events',{request_id:requestId(),reason:'캘린더 일정 복사',...values});await selectCreated(result,values.event_date,{keepOpen:true});text('editor-status','선택한 날짜에 복사했습니다.');}catch(x){text('editor-status','복사하지 못했습니다: '+(x.detail||x.status||''));}});
$('delete-event').addEventListener('click',async()=>{if(!state.selected||!confirm('이 항목을 삭제할까요?'))return;const item=state.selected;try{await post('/portal/api/admin/learning/calendar-events/update',{request_id:requestId(),reason:'캘린더 일정 삭제',event_id:item.event_id,version:item.version,display_kind:item.display_kind,event_date:item.event_date,end_date:item.end_date||null,color_hex:item.color_hex,course_label:item.course_label,content_text:item.content_text||'',deleted:true});state.month=(item.event_date||state.month).slice(0,7);await loadMonth();$('calendar-editor').close();text('calendar-status','삭제했습니다.');}catch(x){text('editor-status','삭제하지 못했습니다: '+(x.detail||x.status||''));}});
$('logout').addEventListener('click',async()=>{try{const t=await csrf();await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':t}});location.href='/';}catch{text('action-status','로그아웃하지 못했습니다.');}});
boot();
})();
