/* Progressive same-origin login selector. Provider authentication remains a native POST/redirect. */
'use strict';
(() => {
  const returnPaths = new Set(['/','/index.html','/apply.html','/portal/mypage','/portal/admin','/portal/enrollments','/portal/manual']);
  const providers = {kakao:{label:'카카오 로그인',width:896,height:92},naver:{label:'네이버 로그인',width:1472,height:192}};
  let dialog, content, previousFocus, controller, generation = 0;
  const node = (tag, text, cls) => {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
  function safeNotice(markup) {
    const allowed = new Set(['DETAILS','SUMMARY','SPAN','TABLE','CAPTION','THEAD','TBODY','TR','TH','TD','P','A','BR','STRONG']);
    const source = new DOMParser().parseFromString(markup,'text/html').querySelector('details.collection-notice');
    if(!source) throw new Error('invalid_notice');
    function copy(input) {
      if(input.nodeType===Node.TEXT_NODE)return document.createTextNode(input.textContent);
      if(input.nodeType!==Node.ELEMENT_NODE || !allowed.has(input.tagName))return document.createTextNode('');
      const output=document.createElement(input.tagName.toLowerCase());
      if(input.tagName==='A') {
        const url=new URL(input.getAttribute('href') || '', location.origin);
        if(url.origin!==location.origin || !['/terms.html','/privacy.html'].includes(url.pathname) || url.search || url.hash)throw new Error('invalid_notice_link');
        output.href=url.pathname;output.target='_blank';output.rel='noopener noreferrer';
      }
      for(const child of input.childNodes)output.append(copy(child));
      return output;
    }
    const clean=copy(source);clean.className='collection-notice';return clean;
  }
  function clear() {generation++;controller?.abort();content?.replaceChildren();}
  function buildDialog() {
    dialog=node('dialog',undefined,'richon-dialog');dialog.id='richon-login-dialog';dialog.setAttribute('aria-labelledby','richon-login-title');
    const close=node('button','×','richon-dialog-close');close.type='button';close.setAttribute('aria-label','로그인 창 닫기');
    const title=node('h2','간편 로그인');title.id='richon-login-title';
    content=node('div');dialog.append(close,title,content);document.body.append(dialog);
    close.addEventListener('click',()=>dialog.close());
    dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();});
    dialog.addEventListener('close',()=>{if(dialog.open)return;clear();if(previousFocus?.isConnected)previousFocus.focus();});
  }
  async function open(trigger) {
    const target=returnPaths.has(location.pathname)?location.pathname:'/';
    if(!window.HTMLDialogElement || typeof HTMLDialogElement.prototype.showModal!=='function') {location.assign('/auth/login?return_to='+encodeURIComponent(target));return;}
    if(!dialog)buildDialog();if(dialog.open)return;
    clear();previousFocus=trigger;const serial=generation;
    const status=node('p','불러오는 중입니다.','richon-login-status');status.setAttribute('role','status');content.append(status);dialog.showModal();
    controller=new AbortController();const timer=setTimeout(()=>controller.abort(),12000);
    try {
      const response=await fetch('/auth/login?view=modal&return_to='+encodeURIComponent(target),{credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,headers:{Accept:'application/json'}});
      if(!response.ok || !response.headers.get('content-type')?.startsWith('application/json'))throw new Error('login_unavailable');
      const data=await response.json();
      if(serial!==generation || !dialog.open)return;
      if(!data || !/^[a-f0-9]{64}$/.test(data.csrf) || data.return_to!==target || typeof data.collect_profile!=='boolean'
          || !Array.isArray(data.providers) || !data.providers.length || data.providers.length>2
          || new Set(data.providers).size!==data.providers.length || data.providers.some(p=>!Object.hasOwn(providers,p)))throw new Error('invalid_login_configuration');
      const form=node('form',undefined,'richon-login-form');form.method='post';form.action='/auth/start';
      const hidden=(name,value)=>{const field=node('input');field.type='hidden';field.name=name;field.value=value;form.append(field);return field;};
      hidden('csrf',data.csrf);hidden('return_to',target);const provider=hidden('provider','');
      if(data.collect_profile){const label=node('label');const field=node('input');field.type='checkbox';field.name='over14';field.value='yes';field.required=true;label.append(field,document.createTextNode(' 만 14세 이상입니다.'));form.append(label);}
      let submitting=false;
      form.addEventListener('submit',event=>{if(submitting){event.preventDefault();return;}submitting=true;});
      for(const name of data.providers){const spec=providers[name];const button=node('button',undefined,'provider-login '+name+'-login');button.type='button';button.setAttribute('aria-label',spec.label);const img=node('img');img.src='/auth/assets/'+name+'-login.png';img.alt=spec.label;img.width=spec.width;img.height=spec.height;img.referrerPolicy='no-referrer';button.append(img);button.addEventListener('click',()=>{if(submitting)return;provider.value=name;form.requestSubmit();});form.append(button);}
      const children=[form];
      if(data.collect_profile){if(typeof data.notice!=='string'||data.notice.length>8000)throw new Error('invalid_notice');children.push(safeNotice(data.notice));}
      content.replaceChildren(...children);
    } catch {
      if(serial!==generation || !dialog.open)return;
      const message=node('p','로그인을 불러오지 못했습니다.','richon-login-status');message.setAttribute('role','alert');
      const fallback=node('a','로그인 화면 열기','site-btn site-btn-line');fallback.href='/auth/login?return_to='+encodeURIComponent(target);
      content.replaceChildren(message,fallback);
    } finally {clearTimeout(timer);}
  }
  document.addEventListener('click',event=>{
    const trigger=event.target.closest?.('[data-richon-login]');
    if(!trigger || event.defaultPrevented || event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)return;
    event.preventDefault();open(trigger);
  });
  window.addEventListener('pagehide',()=>{clear();if(dialog?.open)dialog.close();});
})();
