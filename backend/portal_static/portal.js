/* Same-origin APIs only. No stored tokens, inline handlers, HTML injection or mock login. */
'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const admin = document.body.dataset.page === 'admin';
  const state = {tab: 'orders', offset: 0, limit: 20, hasMore: false, request: 0, unlocked: false};
  const profileFields = ['phone', 'email', 'age', 'gender', 'consultation', 'consented'];
  const ageLabels = {'14-19':'14~19세','20-29':'20~29세','30-39':'30~39세','40-49':'40~49세','50-59':'50~59세','60-69':'60~69세','70+':'70세 이상'};
  const genderLabels = {female:'여성', male:'남성'};
  const labels = {kakao: '카카오', naver: '네이버', member: '일반 회원', admin: '관리자', active: '이용 중', disabled: '이용 정지'};
  const date = (v) => new Intl.DateTimeFormat('ko-KR', {year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Asia/Seoul'}).format(new Date(v));
  const money = (v) => new Intl.NumberFormat('ko-KR').format(v) + '원';
  const text = (id, v) => { if ($(id)) $(id).textContent = String(v); };
  function element(tag, value, cls) { const el = document.createElement(tag); if (value !== undefined) el.textContent = String(value); if (cls) el.className = cls; return el; }
  function pill(value, cls='orange') { return element('span', value, 'pill ' + cls); }
  function gate(title, message, retry=false) {
    state.unlocked = false; state.request += 1;
    $('content').hidden = true; $('gate').hidden = false; $('logout').hidden = true;
    if ($('admin-link')) $('admin-link').hidden = true;
    // Do not retain previously rendered private rows after auth loss/logout.
    for (const id of ['list','table-body','providers']) if ($(id)) $(id).replaceChildren();
    for (const id of ['welcome-name','profile-name','joined','order-count','members-total','courses-total','pending-total']) text(id, '');
    for (const key of profileFields) { text('profile-'+key, ''); if ($('profile-'+key+'-row')) $('profile-'+key+'-row').hidden = true; }
    text('avatar', ''); text('profile-name-label', '표시 이름');
    text('gate-title', title); text('gate-text', message); $('retry-gate').hidden = !retry;
  }
  function authError(error) {
    if (error.status === 401) { gate('로그인이 필요합니다.', '간편 로그인 연동 후 이용할 수 있습니다. 로그인 상태가 만료되었다면 다시 로그인해 주세요.'); return true; }
    if (error.status === 403) { gate('관리자만 이용할 수 있습니다.', '관리자 권한이 있는 계정으로 로그인해 주세요. 일반 회원에게는 고객 정보를 제공하지 않습니다.'); return true; }
    return false;
  }
  async function api(path, options={}) {
    if (!path.startsWith('/portal/api/') && !['/auth/me','/auth/csrf','/auth/logout'].includes(path)) throw new Error('unsupported_path');
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(path, {credentials:'same-origin', cache:'no-store', redirect:'error', signal:controller.signal, ...options});
      if (!response.ok) { const error = new Error('request_failed'); error.status = response.status; throw error; }
      return response.status === 204 ? null : await response.json();
    } finally { clearTimeout(timer); }
  }
  function providerBadges(values) {
    const box = element('div', undefined, 'providers');
    values.forEach(v => box.append(pill(labels[v] || '알 수 없음', 'dark')));
    if (!values.length) box.append(element('span', '연결 정보 없음', 'small'));
    return box;
  }
  function showProfile(profile) {
    // The server returns registration only on the authenticated user's own API.
    // Legacy accounts do not invent a real name from a nickname.
    const info = profile.registration;
    const registered = info && typeof info.name === 'string' && typeof info.phone === 'string' && typeof info.email === 'string';
    const displayName = registered ? info.name : profile.display_name;
    text('welcome-name', displayName); text('profile-name', displayName);
    text('profile-name-label', registered ? '이름' : '표시 이름');
    text('avatar', [...displayName][0] || 'R'); text('joined', date(profile.created_at));
    for (const key of profileFields) { text('profile-'+key, ''); $('profile-'+key+'-row').hidden = !registered; }
    if (registered) {
      const consented = info.consultation_consent === true;
      text('profile-phone', info.phone); text('profile-email', info.email);
      // Optional data must stay invisible without affirmative consent, even if
      // an unexpected upstream response contains a value.
      text('profile-age', consented ? (Object.hasOwn(ageLabels, info.age_range) ? ageLabels[info.age_range] : '선택하지 않음') : '제공하지 않음');
      text('profile-gender', consented ? (Object.hasOwn(genderLabels, info.gender) ? genderLabels[info.gender] : '선택하지 않음') : '제공하지 않음');
      text('profile-consultation', consented ? '동의' : '동의하지 않음');
      const acceptedAt = new Date(info.consented_at);
      text('profile-consented', info.consented_at && Number.isFinite(acceptedAt.getTime()) ? date(acceptedAt) : '확인 필요');
    }
    text('order-count', profile.linked_order_count); $('providers').replaceChildren(providerBadges(profile.providers));
    $('admin-link').hidden = profile.role !== 'admin';
  }
  function renderOrders(items) {
    const root = $('list'); root.replaceChildren();
    if (!items.length) { const empty = element('div', undefined, 'empty'); empty.append(element('div','▤','empty-symbol'),element('strong','연결된 신청·주문 내역이 없습니다.'),element('span','이전 비회원 신청은 본인 확인 후 연결할 예정입니다.')); root.append(empty); return; }
    for (const row of items) {
      const card = element('article', undefined, 'order-card'); const left = element('div');
      left.append(pill(row.status === 'pending_payment' ? '결제 대기' : '상태 확인 필요'), element('h3', row.course_title));
      left.append(element('div', (row.cohort || '기수 없음') + ' / ' + date(row.created_at), 'order-meta'));
      left.append(element('div', '주문번호 ' + row.order_id, 'order-meta'));
      card.append(left, element('div',money(row.amount_krw),'price mono')); root.append(card);
    }
  }
  const configs = {
    orders: {title:'신청·주문 내역', description:'연결되지 않은 비회원 주문도 함께 확인합니다.', search:'신청자 이름 / 주문번호 / 연락처 검색', placeholder:'이름 또는 정확한 주문번호·전화번호·이메일', filter:'회원 연결', key:'linked', options:[['','전체'],['true','연결됨'],['false','미연결']], heads:['신청자','강의 / 기수','주문 금액','상태','신청일']},
    members: {title:'회원 목록', description:'회원과 연결된 로그인 종류를 확인합니다. 비회원 신청자는 주문 목록에서 확인하세요.', search:'회원 이름 / 회원번호 검색', placeholder:'표시 이름 또는 정확한 회원번호', filter:'회원 상태', key:'status', options:[['','전체'],['active','이용 중'],['disabled','이용 정지']], heads:['회원','로그인 계정','역할 / 상태','연결된 주문','가입일']},
    courses: {title:'강의 목록', description:'서버에 등록된 강의와 가격입니다. 수강기간과 수강 확정은 아직 관리하지 않습니다.', search:'강의명 / 기수 검색', placeholder:'강의명, 기수 또는 정확한 강의 ID', filter:'신청 가능', key:'enabled', options:[['','전체'],['true','가능'],['false','중지']], heads:['강의 / 기수','수강료','신청 상태','등록일']}
  };
  function primary(main, sub) { const box=element('div'); box.append(element('div',main,'primary-text')); if (sub) box.append(element('div',sub,'secondary')); return box; }
  function renderTable(items) {
    const cfg = configs[state.tab]; const header=element('tr'); cfg.heads.forEach(h => {const th=element('th',h); th.scope='col'; header.append(th);}); $('table-head').replaceChildren(header);
    const body=$('table-body'); body.replaceChildren();
    if (!items.length) {const tr=element('tr',undefined,'table-empty');const td=element('td','조건에 맞는 내역이 없습니다.'); td.colSpan=cfg.heads.length; tr.append(td); body.append(tr); return;}
    for(const row of items) {
      let cells;
      if(state.tab==='orders') cells=[primary(row.customer_name, row.phone_masked+' / '+row.email_masked),primary(row.course_title,(row.cohort||'기수 없음')+' / '+row.order_id),element('span',money(row.amount_krw),'nowrap mono'),primary(row.status==='pending_payment'?'결제 대기':'상태 확인 필요',row.member_linked?'회원 연결됨':'회원 미연결'),element('span',date(row.created_at),'nowrap')];
      else if(state.tab==='members') cells=[primary(row.display_name,row.member_id),providerBadges(row.providers),primary(labels[row.role]||'확인 필요',labels[row.status]||'확인 필요'),element('span',row.linked_order_count+'건','mono'),element('span',date(row.created_at),'nowrap')];
      else cells=[primary(row.title,(row.cohort||'기수 없음')+' / '+row.course_id),element('span',money(row.price_krw),'nowrap mono'),pill(row.enabled?'신청 가능':'신청 중지',row.enabled?'green':'dark'),element('span',date(row.created_at),'nowrap')];
      const tr=element('tr'); cells.forEach(child=>{const td=element('td'); td.append(child); tr.append(td);});body.append(tr);
    }
  }
  async function summary() {
    if (!state.unlocked) return;
    try {
      const data=await api('/portal/api/admin/summary'); if (!state.unlocked) return;
      text('members-total',data.members_total);text('members-note','이용 중 '+data.members_active+'명');
      text('courses-total',data.courses_total);text('courses-note','신청 가능 '+data.courses_enabled+'개');
      text('pending-total',data.pending_orders);text('orders-note','전체 '+data.orders_total+'건 / 회원 미연결 '+data.unlinked_orders+'건');text('summary-status','');
    } catch(error) {if(authError(error))return;for(const id of ['members-total','courses-total','pending-total']) text(id,'—');text('summary-status','현황을 불러오지 못했습니다. 새로고침으로 다시 확인해 주세요.');}
  }
  async function list() {
    if (!state.unlocked) return;
    const serial=++state.request; $('pager').hidden=true;$('retry-list').hidden=true;text('list-status','불러오는 중입니다.');
    if (admin) { $('table-body').replaceChildren(); $('table-head').replaceChildren(); } else $('list').replaceChildren();
    const query=new URLSearchParams({limit:String(state.limit),offset:String(state.offset)});
    if(admin){query.set('q',$('search').value.trim());if($('filter').value)query.set(configs[state.tab].key,$('filter').value);}
    try {
      const result=await api((admin?'/portal/api/admin/'+state.tab:'/portal/api/me/orders')+'?'+query);
      if(serial!==state.request || !state.unlocked)return;
      admin?renderTable(result.items):renderOrders(result.items);
      state.hasMore=result.has_more; text('list-status','');$('pager').hidden=false;
      text('page-info',result.items.length?`${state.offset+1}–${state.offset+result.items.length}번째 내역`:'표시할 내역 없음');
      $('prev').disabled=state.offset===0;$('next').disabled=!state.hasMore||state.offset+state.limit>10000;
    } catch(error) {
      // Authentication loss must win even when it belongs to a superseded request.
      if(authError(error))return; if(serial!==state.request)return;
      text('list-status',error.status===422?'검색 조건을 확인해 주세요.':'목록을 불러오지 못했습니다. 저장된 정보가 없다는 의미는 아닙니다.');$('retry-list').hidden=false;
    }
  }
  async function boot() {
    gate(admin?'관리자 권한을 확인하고 있습니다.':'로그인 상태를 확인하고 있습니다.','잠시만 기다려 주세요.');
    const serial = state.request;
    try {
      const me=await api('/portal/api/me');
      if (serial !== state.request) return;
      if(admin && me.role!=='admin'){gate('관리자만 이용할 수 있습니다.','관리자 권한이 있는 계정으로 로그인해 주세요.');return;}
      state.unlocked=true;$('gate').hidden=true;$('content').hidden=false;$('logout').hidden=false;
      if(admin)await Promise.all([summary(),list()]);else{showProfile(me);await list();}
    }catch(error){if(serial !== state.request)return;if(!authError(error))gate('지금 정보를 불러올 수 없습니다.','연결 상태를 확인한 후 다시 시도해 주세요. 데이터가 없다는 의미는 아닙니다.',true);}
  }
  $('retry-gate').addEventListener('click',boot);$('retry-list').addEventListener('click',list);
  $('refresh').addEventListener('click',()=>{list();if(admin)summary();});
  $('prev').addEventListener('click',()=>{if(state.offset>0){state.offset-=state.limit;list();}});
  $('next').addEventListener('click',()=>{if(state.hasMore){state.offset+=state.limit;list();}});
  if(admin){
    document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{
      state.tab=button.dataset.tab;state.offset=0;$('search').value='';const cfg=configs[state.tab];
      text('list-title',cfg.title);text('list-description',cfg.description);text('search-label',cfg.search);text('filter-label',cfg.filter);$('search').placeholder=cfg.placeholder;
      $('filter').replaceChildren(...cfg.options.map(([v,t])=>{const el=element('option',t);el.value=v;return el;}));
      document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));list();
    }));
    $('search-form').addEventListener('submit',event=>{event.preventDefault();state.offset=0;list();});
  }
  $('logout').addEventListener('click',async()=>{
    $('logout').disabled=true;text('action-status','');
    try{const csrf=await api('/auth/csrf');await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf.csrf_token}});gate('로그아웃되었습니다.','다시 이용하려면 간편 로그인해 주세요.');}
    catch(error){if(!authError(error))text('action-status','로그아웃을 완료하지 못했습니다. 다시 시도해 주세요.');}
    finally{$('logout').disabled=false;}
  });
  window.addEventListener('pageshow',event=>{if(event.persisted)boot();});
  window.addEventListener('pagehide',()=>gate('로그인 상태를 확인하고 있습니다.','잠시만 기다려 주세요.'));
  boot();
})();