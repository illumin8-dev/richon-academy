/* PortOne only starts the identity-verification UI. Final trust is server-side. */
'use strict';
(() => {
  const form=document.querySelector('form[data-richon-signup]');
  const box=form&&form.querySelector('[data-richon-identity]');
  if(!form||!box)return;

  const button=box.querySelector('[data-richon-identity-start]');
  const status=box.querySelector('[data-richon-identity-status]');
  const hidden=form.querySelector('input[name="identity_verification_id"]');
  const submit=form.querySelector('[data-richon-signup-submit]');
  const expected=box.dataset.verificationId||'';

  function complete(id){
    if(id!==expected)return false;
    hidden.value=id;
    box.dataset.identityVerified='true';
    status.textContent='본인확인이 완료되었습니다. 가입을 계속해 주세요.';
    button.hidden=true;
    submit.disabled=false;
    return true;
  }

  if(box.dataset.identityVerified==='true'&&hidden.value===expected){
    complete(expected);
    return;
  }
  submit.disabled=true;

  button.addEventListener('click',async()=>{
    if(!window.PortOne||typeof window.PortOne.requestIdentityVerification!=='function'){
      status.textContent='본인확인 모듈을 불러오지 못했습니다. 페이지를 새로고침해 주세요.';
      return;
    }
    button.disabled=true;
    status.textContent='본인확인 화면을 여는 중입니다.';
    try{
      const response=await window.PortOne.requestIdentityVerification({
        storeId:box.dataset.storeId,
        channelKey:box.dataset.channelKey,
        identityVerificationId:expected,
        redirectUrl:box.dataset.redirectUrl
      });
      // Redirect-based mobile flows leave this page and return to redirectUrl.
      if(!response)return;
      if(response.code!==undefined){
        status.textContent='본인확인을 완료하지 못했습니다. 다시 시도해 주세요.';
        return;
      }
      if(!complete(response.identityVerificationId||'')){
        status.textContent='본인확인 결과를 확인하지 못했습니다. 다시 시도해 주세요.';
      }
    }catch(_error){
      status.textContent='본인확인을 완료하지 못했습니다. 다시 시도해 주세요.';
    }finally{
      if(box.dataset.identityVerified!=='true')button.disabled=false;
    }
  });
})();
