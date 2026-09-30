'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const API = '/portal/api/admin/enrollments';
  const stateText = {scheduled:'시작 전',active:'수강 중',ended:'종료',pending:'미확정'};
  const payText = {unknown:'미확인',pending:'결제 대기',recorded:'확인 기록',refunded:'환불 기록'};
  const receiptText = {unknown:'미확인',not_requested:'미요청',requested:'발급 요청',recorded_issued:'발급 기록'};
  const grantText = {pending:'확정 대기',confirmed:'수강 확정',cancelled:'취소'};
  const requests = new Set();
  let epoch = 0, searchSeq = 0, historySeq = 0, csrf = '', offset = 0, current = null;
  let selected = null, historyOffset = 0;
  function node(tag,text,className) { const e=document.createElement(tag); if(text!==undefined)e.textContent=String(text); if(className)e.className=className; return e; }
  function seoulMonth() { const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit'}).formatToParts(new Date()); return p.find(x=>x.type==='year').value+'-'+p.find(x=>x.type==='month').value; }
  function monthText(s) { if(!s)return '—'; const [y,m]=s.split('-'); return y+'년 '+Number(m)+'월'; }
  function period(a,b) { if(!b)return monthText(a)+' 시작 / 미확정'; if(a===b)return monthText(a); if(a.slice(0,4)===b.slice(0,4))return a.slice(0,4)+'년 '+Number(a.slice(5))+'~'+Number(b.slice(5))+'월'; return monthText(a)+' ~ '+monthText(b); }
  function money(v) { return v===null||v===undefined?'—':new Intl.NumberFormat('ko-KR').format(v)+'원'; }
  function dateText(v) { return v?new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(v)):'—'; }
  const columns = [
    ['name','이름',r=>r.name,true],['nickname','닉네임',r=>r.nickname||'—',true],
    ['course','수강 과정 / 기수',r=>r.course_title,true],['period','확정 수강월',r=>period(r.start_month,r.end_month),true],
    ['months','누적 확정기간',r=>r.confirmed_months+'개월',true],['plan','최근 신청기간',r=>r.last_plan_months?r.last_plan_months+'개월':'—',true],
    ['status','조회 월 수강상태',r=>stateText[r.status],true],['quoted','최근 신청금액',r=>money(r.latest_quoted_krw),true],
    ['paid','결제기록 합계 (환불반영)',r=>money(r.net_recorded_paid_krw),true],
    ['payment','최근 결제기록',r=>payText[r.latest_payment_state]||'미확인',false],
    ['receipt','최근 현금영수증',r=>receiptText[r.latest_receipt_state]||'미확인',true],
    ['email','이메일 (보호)',r=>r.email_masked||'—',true],['phone','전화번호 (보호)',r=>r.phone_masked||'—',true],
    ['applied','최근 신청일',r=>dateText(r.last_applied_at),false],['joined','회원가입일',r=>r.member_linked?dateText(r.joined_at):'비회원 / 미연결',false],
    ['refunded','누적 환불기록',r=>money(r.refunded_krw),false],['count','구매 / 연장 이력',r=>r.term_count+'건',false],
  ];
  let visible = new Set(columns.filter(c=>c[3]).map(c=>c[0]));
  async function request(path,options={}) {
    const controller=new AbortController(); requests.add(controller);
    const timer=setTimeout(()=>controller.abort(),15000);
    try { const r=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',...options,signal:controller.signal});
      if(!r.ok){const e=new Error('request_failed');e.status=r.status;throw e;}
      return r.status===204?null:await r.json();
    } finally { clearTimeout(timer); requests.delete(controller); }
  }
  function clearData() {
    epoch++; searchSeq++; historySeq++; csrf='';current=null;selected=null;
    requests.forEach(r=>r.abort());requests.clear();
    ['table-head','table-body','course-counts','history-body'].forEach(id=>$(id).replaceChildren());
    ['stat-people','stat-enrollments','stat-ending','stat-pending','total'].forEach(id=>$(id).textContent='—');
    $('history-title').textContent='신청 / 연장 이력';$('history-subtitle').textContent='';$('history-message').textContent='';
    if($('history').open)$('history').close();
    $('content').hidden=true;$('logout').hidden=true;
    $('search').value='';$('page-info').textContent='';$('list-message').textContent='';
  }
  function gate(title,text) { clearData();$('gate').hidden=false;$('gate-title').textContent=title;$('gate-text').textContent=text;$('retry').hidden=false; }
  function accessError(e) { if(e.status===401||e.status===403){gate('접근 권한을 다시 확인해 주세요.','로그인이 만료되었거나 관리자 권한·보안 확인이 필요합니다.');return true;}return false; }
  function settings() {
    const list=$('column-list');list.replaceChildren();
    columns.forEach(([key,label])=>{const wrap=node('label');const check=node('input');check.type='checkbox';check.checked=visible.has(key);check.disabled=key==='name';
      check.addEventListener('change',()=>{check.checked?visible.add(key):visible.delete(key);if(current)renderRows(current.items);});
      wrap.append(check,node('span',label));list.append(wrap);});
  }
  function renderRows(items) {
    const active=columns.filter(c=>visible.has(c[0]));const head=node('tr');active.forEach(c=>head.append(node('th',c[1])));$('table-head').replaceChildren(head);$('table-body').replaceChildren();
    items.forEach(r=>{const tr=node('tr');active.forEach(([key,,format])=>{const td=node('td');
      if(key==='name'){const b=node('button',r.name,'name-button');b.addEventListener('click',()=>openHistory(r));td.append(b);if(!r.member_linked)td.append(node('small','비회원 / 미연결'));}
      else if(key==='course'){td.append(node('span',r.course_title));td.append(node('small',r.cohort||'기수 없음'));}
      else if(key==='status'){td.append(node('span',stateText[r.status],'badge '+r.status));if(r.pending_terms)td.append(node('small','확정 대기 '+r.pending_terms+'건'));}
      else {td.textContent=format(r);if(key==='period')td.className='month-period';if(['quoted','paid','refunded'].includes(key))td.className='number';}
      tr.append(td);});$('table-body').append(tr);});
  }
  function body() {
    return {month:$('month').value,scope:$('all-months').checked?'all':'month',course_id:$('course').value||null,
      q:$('search').value.trim(),plan_months:$('plan').value?Number($('plan').value):null,status:$('status').value||null,
      payment_state:$('payment').value||null,receipt_state:$('receipt').value||null,
      member_linked:$('linked').value===''?null:$('linked').value==='true',
      end_from:$('end-from').value||null,end_to:$('end-to').value||null,limit:Number($('page-size').value),offset};
  }
  async function load() {
    const version=epoch,seq=++searchSeq;
    $('table-body').replaceChildren();$('course-counts').replaceChildren();current=null;
    ['stat-people','stat-enrollments','stat-ending','stat-pending','total'].forEach(id=>$(id).textContent='—');
    $('list-message').textContent='수강 현황을 불러오고 있습니다.';$('retry-list').hidden=true;$('prev').disabled=true;$('next').disabled=true;
    $('search-button').disabled=true;$('page-info').textContent='';
    try {
      if(!csrf)throw new Error('missing_csrf');
      const data=await request(API+'/search',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body())});
      if(version!==epoch||seq!==searchSeq)return;
      current=data;renderRows(data.items);const s=data.summary;
      $('stat-people').textContent=s.confirmed_people+'명';$('stat-enrollments').textContent=s.confirmed_enrollments+'건';
      $('stat-ending').textContent=s.ending_people+'명';$('stat-pending').textContent=s.pending_people+'명';$('total').textContent=s.total+'행';
      data.courses.forEach(c=>{const b=node('button');b.type='button';b.setAttribute('aria-pressed',String(c.course_id===$('course').value));
        b.append(node('span',c.course_title+(c.cohort?' / '+c.cohort:'')),node('b',c.confirmed_people+'명'),node('span',' / 대기 '+c.pending_people+'명'));
        b.addEventListener('click',()=>{$('course').value=$('course').value===c.course_id?'':c.course_id;offset=0;load();});$('course-counts').append(b);});
      if(data.courses_truncated)$('course-counts').append(node('span','과정 요약은 처음 200개까지 표시합니다.','hint'));
      $('list-message').textContent=data.items.length?'':'조건에 맞는 수강 내역이 없습니다.';
      $('page-info').textContent=data.items.length?(data.offset+1)+'–'+(data.offset+data.items.length)+' / 총 '+s.total+'행':'총 '+s.total+'행';
      $('result-note').textContent=monthText(data.month)+' 기준 / 현재 필터 전체 집계 / 이름을 누르면 구매·연장 이력을 확인합니다.';
      $('prev').disabled=offset===0;$('next').disabled=!data.has_more;
    } catch(e) { if(version!==epoch||seq!==searchSeq)return;if(!accessError(e)){$('list-message').textContent=e.status===422?'필터 값을 확인해 주세요. 종료월 범위가 올바른지도 확인해 주세요.':'조회하지 못했습니다. 다시 불러와 주세요.';$('retry-list').hidden=false;} }
    finally {if(version===epoch&&seq===searchSeq)$('search-button').disabled=false;}
  }
  async function initialize() {
    clearData();const version=epoch;$('gate').hidden=false;$('gate-title').textContent='관리자 권한을 확인하고 있습니다.';$('gate-text').textContent='잠시만 기다려 주세요.';$('retry').hidden=true;
    try {
      const me=await request('/auth/me');if(version!==epoch)return;
      if(me.role!=='admin'){gate('관리자 전용 화면입니다.','일반 회원은 마이페이지를 이용해 주세요.');return;}
      const token=await request('/auth/csrf');if(version!==epoch)return;csrf=token.csrf_token;
      const choices=await request(API+'/options');if(version!==epoch)return;
      const old=$('course').value;$('course').replaceChildren(new Option('전체 과정 / 기수',''));
      choices.items.forEach(c=>$('course').add(new Option(c.title+(c.cohort?' / '+c.cohort:''),c.course_id)));
      if([...$('course').options].some(o=>o.value===old))$('course').value=old;
      $('action-message').textContent=choices.has_more?'과정 선택은 처음 200개만 표시됩니다.':'';
      $('gate').hidden=true;$('content').hidden=false;$('logout').hidden=false;await load();
    } catch(e) {if(version!==epoch)return;if(!accessError(e))gate('관리 화면을 불러오지 못했습니다.','로그인 연결과 서버 상태를 확인한 뒤 다시 시도해 주세요.');}
  }
  function pair(label,value){const d=node('div');d.append(node('span',label),node('b',value));return d;}
  async function loadHistory() {
    const row=selected;if(!row)return;const version=epoch,seq=++historySeq;
    $('history-body').replaceChildren();$('history-message').textContent='이력을 불러오고 있습니다.';$('history-prev').disabled=true;$('history-next').disabled=true;
    try { const data=await request(API+'/'+encodeURIComponent(row.enrollment_id)+'/terms?limit=20&offset='+historyOffset);
      if(version!==epoch||seq!==historySeq||!$('history').open)return;
      data.items.forEach(t=>{const card=node('article',undefined,'history-card');card.append(node('h3',(t.sequence_no===1?'최초 신청':'추가 신청 / 연장')+' / '+t.months+'개월 / '+grantText[t.grant_state]));
        const g=node('div',undefined,'history-grid');g.append(pair('확정 수강월',t.end_month?period(t.start_month,t.end_month):'미확정 / 기간에 미반영'),pair('신청일',dateText(t.applied_at)),pair('신청금액',money(t.quoted_amount_krw)),pair('결제기록',payText[t.payment_state]),pair('기록된 결제금액',money(t.paid_amount_krw)),pair('환불기록',money(t.refunded_amount_krw)),pair('결제기록일',dateText(t.paid_at)),pair('현금영수증',receiptText[t.receipt_state]),pair('주문번호',t.order_id||'아직 미연결'));card.append(g);$('history-body').append(card);});
      $('history-message').textContent=data.items.length?'':'신청 이력이 없습니다.';$('history-prev').disabled=historyOffset===0;$('history-next').disabled=!data.has_more;
    } catch(e){if(version!==epoch||seq!==historySeq)return;if(!accessError(e))$('history-message').textContent='이력을 불러오지 못했습니다. 닫은 뒤 다시 열어 주세요.';}
  }
  function openHistory(row){selected=row;historyOffset=0;$('history-title').textContent=row.name+' / '+(row.nickname||'닉네임 미등록');$('history-subtitle').textContent=row.course_title+' / '+period(row.start_month,row.end_month);$('history').showModal();loadHistory();}
  if(!$('month').value)$('month').value=seoulMonth();
  $('filters').addEventListener('submit',e=>{e.preventDefault();offset=0;load();});
  ['month','course','plan','status','payment','receipt','linked','all-months','page-size'].forEach(id=>$(id).addEventListener('change',()=>{if(id==='status'&&['scheduled','ended'].includes($('status').value))$('all-months').checked=true;offset=0;load();}));
  ['month-prev','month-next'].forEach((id,i)=>$(id).addEventListener('click',()=>{const [y,m]=$('month').value.split('-').map(Number);const n=y*12+m-1+(i?1:-1);const year=Math.floor(n/12);if(year<1||year>9999)return;$('month').value=String(year).padStart(4,'0')+'-'+String(n%12+1).padStart(2,'0');offset=0;load();}));
  $('reset').addEventListener('click',()=>{const month=$('month').value;HTMLFormElement.prototype.reset.call($('filters'));$('month').value=month;offset=0;load();});
  $('prev').addEventListener('click',()=>{offset=Math.max(0,offset-Number($('page-size').value));load();});$('next').addEventListener('click',()=>{offset+=Number($('page-size').value);load();});
  $('retry').addEventListener('click',initialize);$('retry-list').addEventListener('click',load);
  $('columns-reset').addEventListener('click',()=>{visible=new Set(columns.filter(c=>c[3]).map(c=>c[0]));settings();if(current)renderRows(current.items);});
  $('history-close').addEventListener('click',()=>$('history').close());$('history').addEventListener('close',()=>{historySeq++;selected=null;$('history-body').replaceChildren();});
  $('history-prev').addEventListener('click',()=>{historyOffset=Math.max(0,historyOffset-20);loadHistory();});$('history-next').addEventListener('click',()=>{historyOffset+=20;loadHistory();});
  $('logout').addEventListener('click',async()=>{try{await request('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf}});gate('로그아웃되었습니다.','다시 로그인한 뒤 이용해 주세요.');}catch(e){if(!accessError(e))$('action-message').textContent='로그아웃을 완료하지 못했습니다. 다시 시도해 주세요.';}});
  window.addEventListener('pagehide',clearData);window.addEventListener('pageshow',e=>{if(e.persisted)initialize();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clearData();else initialize();});
  settings();initialize();
})();
