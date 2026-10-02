(() => {
  'use strict';
  const config=document.body.dataset;
  const FORM_URL=config.formUrl||'';
  const PAYMENT_URL=config.paymentUrl||'';
  const BANK_ACCOUNT=config.bankAccount||'';
  const COURSES={
    pre:{name:'Pre리치온 (프리리치온)',when:'매주 목요일 / 입문 과정',status:'open',price:'수강료 안내',sub:'신청서에서 최종 확인',desc:'부동산 투자원칙·갭투자·서울 초기재개발·시장구조부터 분양권·지방 재개발·경매까지, 실전형 순환 학습으로 기초를 세우는 정규 과정.',thumb:'assets/images/pre-richon-course.jpg',gallery:['assets/apply/pre-01.jpg','assets/apply/pre-02.png','assets/apply/pre-03.png','assets/apply/pre-04.png','assets/apply/pre-05.png','assets/apply/pre-06.png','assets/apply/pre-07.png','assets/apply/pre-08.png','assets/apply/pre-09.png'],info:'기존 강의 소개 기준 2개월(8주) 과정 / 매주 목요일 저녁 9시 / 온라인 ZOOM 라이브',curriculum:[['Week 1','부동산 투자원칙','리치온초이 멘토'],['Week 2','갭투자','가위남 멘토'],['Week 3','서울초기재개발','후니동산 멘토'],['Week 4','부동산 기초 및 시장구조','이루민 멘토'],['Week 5','분양권 전략','키네스트 멘토'],['Week 6','지방 재개발','재부스 멘토'],['Week 7','경매 권리분석 및 수익화','인생공부 멘토'],['Week 8','현장 및 멘토와의 만남','종합 실전 멘토링']]},
    study:{name:'리치온 스터디',when:'매주 일요일 / 실전 과정',status:'open',price:'수강료 안내',sub:'신청서에서 최종 확인',desc:'현금흐름, 갭투자, 서울 초기재개발, 경매 등 매주 실전 주제로 깊이 파고드는 핵심 스터디.',thumb:'assets/images/richon-study-course.jpg',gallery:['assets/apply/study-01.jpg','assets/apply/study-02.jpg','assets/apply/study-03.jpg','assets/apply/study-04.jpg','assets/apply/study-05.jpg','assets/apply/study-06.jpg','assets/apply/study-07.jpg','assets/apply/study-08.jpg','assets/apply/study-09.jpg','assets/apply/study-10.jpg','assets/apply/study-11.jpg','assets/apply/study-12.jpg']},
    redev:{name:'재개발 중급반',when:'매주 화요일 / 중급 과정',status:'waitlist',price:'대기 신청',sub:'결제는 모집 확정 후 안내',desc:'정밀한 입지 분석과 인프라 변화 예측으로 수도권 주요 재개발/재건축 단지를 공략하는 심화 과정.',thumb:'assets/images/redevelopment-reconstruction-course.jpg',gallery:['assets/apply/redevelopment-01.jpg','assets/apply/redevelopment-02.jpg','assets/apply/redevelopment-03.jpg','assets/apply/redevelopment-04.jpg','assets/apply/redevelopment-05.jpg','assets/apply/redevelopment-06.jpg','assets/apply/redevelopment-07.jpg','assets/apply/redevelopment-08.jpg','assets/apply/redevelopment-09.jpg','assets/apply/redevelopment-10.jpg','assets/apply/redevelopment-11.jpg']},
    interior:{name:'리치온 인테리어',when:'매주 수요일 / PREMIUM',status:'upcoming',price:'모집 예정',sub:'모집 시작 전 결제하지 않습니다',desc:'자산 가치를 높이는 공간 디자인 전문 과정. 수익률로 이어지는 인테리어 전략과 공간가치 판단을 다룹니다.',thumb:'assets/images/space-design-course.jpg',gallery:['assets/apply/interior-01.jpg','assets/apply/interior-02.jpg','assets/apply/interior-03.jpg','assets/apply/interior-04.jpg','assets/apply/interior-05.jpg','assets/apply/interior-06.jpg','assets/apply/interior-07.jpg','assets/apply/interior-08.jpg','assets/apply/interior-09.jpg','assets/apply/interior-10.jpg','assets/apply/interior-11.jpg','assets/apply/interior-12.jpg','assets/apply/interior-13.jpg','assets/apply/interior-14.jpg','assets/apply/interior-15.jpg']},
    subscription:{name:'청약 실전반',when:'신규 개설 준비',status:'upcoming',price:'모집 예정',sub:'세부 커리큘럼 확정 후 오픈',desc:'분양권과 청약 흐름을 시장/지역 분석과 연결해 보는 신규 과정입니다. 세부 커리큘럼 확정 후 오픈됩니다.',thumb:'assets/images/subscription-course.jpg',gallery:['assets/apply/subscription-01.jpg','assets/apply/subscription-02.jpg','assets/apply/subscription-03.jpg','assets/apply/subscription-04.jpg','assets/apply/subscription-05.jpg','assets/apply/subscription-06.jpg','assets/apply/subscription-07.jpg','assets/apply/subscription-08.jpg','assets/apply/subscription-09.jpg','assets/apply/subscription-10.jpg']}
  };
  const ORDER=['pre','study','redev','interior','subscription'];
  const STATUS={open:'모집중',waitlist:'대기신청',upcoming:'모집예정'};
  const configured=value=>typeof value==='string'&&value.length>0&&!value.includes('{{')&&!value.includes('}}');
  const setLink=(el,url)=>{
    const ok=configured(url);
    el.setAttribute('aria-disabled',String(!ok));
    if(ok){el.href=url;el.target='_blank';el.rel='noopener noreferrer';}
    else{el.removeAttribute('href');el.removeAttribute('target');el.removeAttribute('rel');}
    return ok;
  };
  const chips=document.getElementById('course-chips');
  const params=new URLSearchParams(location.search);
  let current=COURSES[params.get('course')]?params.get('course'):'pre';

  ORDER.forEach(id=>{
    const course=COURSES[id];
    const button=document.createElement('button');
    button.type='button';
    button.className='apply-chip';
    button.dataset.course=id;
    button.textContent=course.name+' / '+STATUS[course.status];
    button.addEventListener('click',()=>{current=id;render();history.replaceState(null,'','?course='+encodeURIComponent(id));});
    chips.append(button);
  });

  function render(){
    const course=COURSES[current];
    chips.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.course===current)));
    const visual=document.getElementById('course-visual');
    const thumb=document.createElement('img');thumb.src=course.thumb;thumb.alt=course.name+' 과정 썸네일';thumb.decoding='async';
    const badge=document.createElement('span');badge.className='apply-visual-badge';badge.textContent=STATUS[course.status];
    visual.replaceChildren(thumb,badge);
    document.getElementById('course-when').textContent=course.when;
    document.getElementById('course-title').textContent=course.name;
    document.getElementById('course-desc').textContent=course.desc;
    const info=document.getElementById('course-info');
    const curriculum=document.getElementById('course-curriculum');
    if(course.info&&Array.isArray(course.curriculum)){
      document.getElementById('course-info-summary').textContent=course.info;
      curriculum.replaceChildren(...course.curriculum.map(([week,title,mentor])=>{
        const item=document.createElement('li');
        const heading=document.createElement('b');heading.textContent=week+' / '+title;
        const detail=document.createElement('span');detail.textContent=mentor;
        item.append(heading,detail);return item;
      }));
      info.hidden=false;
    }else{
      document.getElementById('course-info-summary').textContent='';
      curriculum.replaceChildren();info.hidden=true;
    }
    const galleryRoot=document.getElementById('course-gallery');
    galleryRoot.replaceChildren(...course.gallery.map((src,index)=>{
      const image=document.createElement('img');image.src=src;image.loading='lazy';image.decoding='async';image.alt=course.name+' 상세 소개 '+(index+1);return image;
    }));
    document.getElementById('summary-name').textContent=course.name;
    document.getElementById('summary-when').textContent=course.when;
    const status=document.getElementById('summary-status');
    status.className='apply-status '+course.status;status.textContent=STATUS[course.status];
    const price=document.getElementById('summary-price');
    price.replaceChildren(document.createTextNode(course.price+' '));
    const priceSmall=document.createElement('small');priceSmall.textContent=course.sub;price.append(priceSmall);

    document.getElementById('open-actions').hidden=course.status!=='open';
    document.getElementById('waitlist-actions').hidden=course.status!=='waitlist';
    document.getElementById('bank-area').hidden=course.status!=='open';

    let ready=true;
    if(course.status==='open'){
      ready=setLink(document.getElementById('form-action'),FORM_URL)&&setLink(document.getElementById('payment-action'),PAYMENT_URL);
      document.getElementById('bank-account').textContent=configured(BANK_ACCOUNT)?BANK_ACCOUNT:'운영 계좌 준비 중';
      ready=ready&&configured(BANK_ACCOUNT);
    }else if(course.status==='waitlist'){
      ready=setLink(document.getElementById('waitlist-action'),FORM_URL);
    }
  }
  render();
})();
