/* Signup consent convenience only. Server validates every required/optional consent. */
'use strict';
(() => {
  const form=document.querySelector('form[data-richon-signup]');
  if(!form)return;
  const all=form.querySelector('[data-consent-all]');
  const items=[...form.querySelectorAll('[data-consent-item]')];
  if(!all||!items.length)return;

  function sync(){
    const checked=items.filter(item=>item.checked).length;
    all.checked=checked===items.length;
    all.indeterminate=checked>0&&checked<items.length;
  }

  all.addEventListener('change',()=>{
    for(const item of items)item.checked=all.checked;
    all.indeterminate=false;
  });
  for(const item of items)item.addEventListener('change',sync);
  sync();
})();
