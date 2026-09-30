/* Signup consent convenience and display-only phone formatting. Server remains authoritative. */
'use strict';
(() => {
  const form=document.querySelector('form[data-richon-signup]');
  if(!form)return;
  const all=form.querySelector('[data-consent-all]');
  const items=[...form.querySelectorAll('[data-consent-item]')];

  function sync(){
    if(!all||!items.length)return;
    const checked=items.filter(item=>item.checked).length;
    all.checked=checked===items.length;
    all.indeterminate=checked>0&&checked<items.length;
  }

  all?.addEventListener('change',()=>{
    for(const item of items)item.checked=all.checked;
    all.indeterminate=false;
  });
  for(const item of items)item.addEventListener('change',sync);
  sync();

  const phone=form.querySelector('input[name="phone"]:not([readonly])');
  const formatPhone=value=>{
    const digits=value.replace(/\D/g,'').slice(0,11);
    if(digits.length<=3)return digits;
    if(digits.length<=7)return digits.slice(0,3)+'-'+digits.slice(3);
    if(digits.length<=10)return digits.slice(0,3)+'-'+digits.slice(3,6)+'-'+digits.slice(6);
    return digits.slice(0,3)+'-'+digits.slice(3,7)+'-'+digits.slice(7);
  };
  if(phone){
    phone.inputMode='numeric';
    phone.addEventListener('input',()=>{phone.value=formatPhone(phone.value);});
    phone.addEventListener('blur',()=>{phone.value=formatPhone(phone.value);});
  }
})();
