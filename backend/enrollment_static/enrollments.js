'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const form = $('filters');
  const states = {pending:'확정 대기', scheduled:'시작 전', active:'수강 중', ended:'종료', cancelled:'취소', needs_review:'기간 확인 필요'};
  const money = (v) => v == null ? '확인 전' : Number(v).toLocaleString('ko-KR') + '원';
  const day = (v) => v ? new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(v)) : '—';
  const month = (v) => v == null ? '—' : v + '개월';
  const columns = [
    ['full_name','이름',true],['nickname','닉네임',true],['course_title','수강 과정',true],['cohort','기수',true],
    ['latest_plan_months','최근 신청 기간',true,month],['total_months','누적 수강기간',true,month],
    ['starts_on','수강 시작일',true,day],['ends_on','수강 종료일',true,day],['remaining_days','남은 기간',true],
    ['enrollment_status','수강 상태',true],['latest_agreed_amount_krw','최근 신청금액',true,money],
    ['latest_discount_krw','할인금액',false,money],['paid_amount_krw','실제 결제금액',true,money],
    ['phone_masked','전화번호',true],['email_masked','이메일',true],
    ['cash_receipt_requested','현금영수증 요청',true,(v)=>v==null?'미확인':v?'요청':'미요청'],
    ['cash_receipt_status','현금영수증 발급',false,()=> '확인 전'],
    ['applied_at','신청일',false,day],['joined_at','회원가입일',false,day],
    ['confirmed_term_count','확정 이용권 수',false],['pending_term_count','대기 이용권 수',false],
    ['agreed_total_krw','확정 이용권 금액 합계',false,money]
  ];
  let offset=0, generation=0, controller=null;
  const visible = new Set(columns.filter(c=>c[2]).map(c=>c[0]));
  const el = (tag,text,cls) => {const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n;};
  function setNotice(text){$('notice').textContent=text;}
  function clear(){ $('rows').replaceChildren();$('metrics').replaceChildren();$('course-counts').replaceChildren();$('content').hidden=true;$('row-count').textContent='';$('page-info').textContent='';$('previous').disabled=true;$('next').disabled=true; }
  function columnVisibility(){document.querySelectorAll('[data-col]').forEach(n=>{n.hidden=!visible.has(n.dataset.col);});}
  columns.forEach(([key,label])=>{
    const th=el('th',label);th.scope='col';th.dataset.col=key;$('columns').append(th);
    const row=el('label');const box=el('input');box.type='checkbox';box.checked=visible.has(key);box.disabled=key==='full_name';
    box.addEventListener('change',()=>{box.checked?visible.add(key):visible.delete(key);columnVisibility();});row.append(box,el('span',label));$('column-options').append(row);
  });
  columnVisibility();
  function render(data){
    $('content').hidden=false;$('as-of').textContent=day(data.as_of)+' 기준 / 한국시간';
    const s=data.summary;$('row-count').textContent=s.enrollment_count+'건 / '+s.learner_count+'명';
    const cards=[['현재 수강생',s.active_learners,'명'],['시작 예정',s.scheduled_enrollments,'건'],['7일 내 종료',s.ending_soon,'건'],['확정 대기',s.pending_enrollments,'건']];
    $('metrics').replaceChildren(...cards.map(([title,n,unit])=>{const c=el('div',null,'metric');c.append(el('p',title),el('strong',n),el('small',unit));return c;}));
    $('course-counts').replaceChildren(...data.courses.map(c=>{
      const b=el('button',null,'course-card');b.type='button';b.append(el('strong',c.course_title+(c.cohort?' / '+c.cohort:'')));
      const t=el('span');t.append('현재 수강 ',el('b',c.active_learners+'명'),' / 시작 예정 '+c.scheduled_enrollments+'건');b.append(t);
      b.addEventListener('click',()=>{$('course-filter').value=c.course_id;offset=0;load();});
      if (![...$('course-filter').options].some(o=>o.value===c.course_id)){const o=el('option',c.course_title+(c.cohort?' / '+c.cohort:''));o.value=c.course_id;$('course-filter').append(o);}
      return b;
    }));
    $('course-limit').hidden=!data.courses_truncated;
    $('rows').replaceChildren(...data.items.map(item=>{
      const row=el('tr');columns.forEach(([key,label,defaultVisible,format])=>{
        const td=el('td');td.dataset.col=key;
        if(key==='enrollment_status')td.append(el('span',states[item[key]]||'확인 필요','badge '+item[key]));
        else if(key==='remaining_days'){
          const active=item.enrollment_status==='active';td.textContent=active?item.remaining_days+'일':'—';if(active&&item.remaining_days<=7)td.className='soon';
        }else td.textContent=format?format(item[key]):(item[key]??'—');
        if(key==='paid_amount_krw'||key==='cash_receipt_status')td.className='dim';
        row.append(td);
      });return row;
    }));
    columnVisibility();
    $('page-info').textContent=data.items.length?(data.offset+1)+'–'+(data.offset+data.items.length)+' / '+s.enrollment_count+'건':'검색 결과가 없습니다.';
    $('previous').disabled=offset===0;$('next').disabled=!data.has_more||offset>=10000;
    setNotice(s.needs_review ? '달력에 같은 날짜가 없는 말일 시작 과정 '+s.needs_review+'건은 종료 규칙 확인이 필요합니다. 기간을 임의로 확정하지 않았습니다.' : data.items.length?'':'조건에 맞는 수강생이 없습니다. 필터를 변경해보세요.');
  }
  async function load(){
    const id=++generation;if(controller)controller.abort();controller=new AbortController();clear();setNotice('수강 현황을 불러오는 중입니다.');
    const query=new URLSearchParams();new FormData(form).forEach((v,k)=>{if(String(v).trim())query.set(k,String(v).trim());});query.set('offset',offset);query.set('limit','20');
    try{
      const response=await fetch('/portal/api/admin/enrollments?'+query,{credentials:'same-origin',mode:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
      if(id!==generation)return;
      if(!response.ok){const e=new Error('request_failed');e.status=response.status;throw e;}
      const data=await response.json();if(id!==generation)return;render(data);
    }catch(e){
      if(id!==generation||e.name==='AbortError')return;clear();
      if(e.status===401||e.status===403){$('course-filter').replaceChildren(el('option','전체 과정'));$('course-filter').options[0].value='';}
      setNotice(e.status===401?'로그인이 필요합니다. 로그인 연결 전에는 실제 명단을 열 수 없습니다.':e.status===403?'관리자 권한이 필요합니다.':e.status===422?'검색 조건을 확인해주세요. 종료일 범위나 입력값이 올바르지 않습니다.':'현황을 불러오지 못했습니다. 새로고침으로 다시 시도해주세요.');
    }
  }
  form.addEventListener('submit',e=>{e.preventDefault();offset=0;load();});
  form.addEventListener('reset',()=>{setTimeout(()=>{offset=0;load();},0);});
  $('refresh').addEventListener('click',load);$('previous').addEventListener('click',()=>{offset=Math.max(0,offset-20);load();});$('next').addEventListener('click',()=>{offset+=20;load();});
  $('logout').addEventListener('click',async()=>{
    ++generation;if(controller)controller.abort();clear();$('course-filter').replaceChildren(el('option','전체 과정'));$('course-filter').options[0].value='';form.elements.q.value='';setNotice('로그아웃 중입니다.');
    try{
      const r=await fetch('/auth/csrf',{credentials:'same-origin',mode:'same-origin',cache:'no-store',redirect:'error'});
      if(r.status===401){setNotice('로그아웃 상태입니다.');return;}if(!r.ok)throw new Error();const d=await r.json();
      const out=await fetch('/auth/logout',{method:'POST',credentials:'same-origin',mode:'same-origin',cache:'no-store',redirect:'error',headers:{'X-CSRF-Token':d.csrf_token}});
      if(!out.ok)throw new Error();setNotice('로그아웃되었습니다.');
    }catch(_){setNotice('로그아웃을 완료하지 못했습니다. 다시 시도해주세요.');}
  });
  window.addEventListener('pagehide',()=>{++generation;if(controller)controller.abort();clear();});
  window.addEventListener('pageshow',e=>{if(e.persisted)load();});
  load();
})();
