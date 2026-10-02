  (() => {
    const nav=document.querySelector('.site-nav');
    const onScroll=()=>nav?.classList.toggle('scrolled',window.scrollY>10);
    onScroll();window.addEventListener('scroll',onScroll,{passive:true});
    const els=document.querySelectorAll('.reveal');
    if(!('IntersectionObserver' in window)){els.forEach(el=>el.classList.add('in'));return;}
    const io=new IntersectionObserver(entries=>entries.forEach(entry=>{
      if(entry.isIntersecting){entry.target.classList.add('in');io.unobserve(entry.target);}
    }),{threshold:.12,rootMargin:'0px 0px -6% 0px'});
    els.forEach((el,i)=>{el.style.transitionDelay=(i%4*70)+'ms';io.observe(el);});
  })();
