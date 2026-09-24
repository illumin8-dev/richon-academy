/* Shared chrome behavior. No identity, token or contact details in browser storage. */
'use strict';
(() => {
  function ready() {
    const burger = document.getElementById('burger');
    const menu = document.getElementById('navMenu');
    const setMenu = (open) => {
      burger?.classList.toggle('open', open); menu?.classList.toggle('show', open);
      burger?.setAttribute('aria-expanded', String(open));
    };
    burger?.addEventListener('click', () => setMenu(burger.getAttribute('aria-expanded') !== 'true'));
    menu?.querySelectorAll('a').forEach(a => a.addEventListener('click', () => setMenu(false)));
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && burger?.getAttribute('aria-expanded') === 'true') {setMenu(false); burger.focus();} });
    document.querySelectorAll('[data-site-year]').forEach(el => {el.textContent = String(new Date().getFullYear());});
    // Home entry remains hidden until a separately approved release changes this explicit markup.
    const entry = document.getElementById('site-account-login');
    if (entry && document.body.dataset.accountEntry === 'enabled') entry.hidden = false;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, {once:true}); else ready();
})();
