'use strict';
(()=>{
const $=id=>document.getElementById(id);
const text=(id,v)=>{if($(id))$(id).textContent=String(v??'');};
const el=(tag,value,cls)=>{const x=document.createElement(tag);if(value!==undefined)x.textContent=String(value);if(cls)x.className=cls;return x;};
const requestId=()=>crypto.randomUUID();
async function api(path,options={}){
 const r=await fetch(path,{credentials:'same-origin',cache:'no-store',redirect:'error',...options});
 if(!r.ok){const e=new Error('request_failed');e.status=r.status;try{e.detail=(await r.json()).detail}catch{}throw e;}
 return r.status===204?null:r.json();
}
async function csrf(){
 const r=await api('/auth/csrf');return r.csrf_token;
}
async function post(path,body){
 const token=await csrf();
 return api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(body)});
}
window.RichonOps=Object.freeze({$,text,el,requestId,api,csrf,post});
})();
