// Wiring of the page's fixed controls and start-up. Loaded last.

function wireGlobalEvents(){
  $$('[data-route]').forEach(el=>el.onclick=()=>routeTo(el.dataset.route));
  $('#sidebar-collapse').onclick=()=>{document.body.classList.toggle('sidebar-collapsed');post('/api/settings',{sidebarCollapsed:document.body.classList.contains('sidebar-collapsed')})};
  $('#user-avatar').onclick=()=>{const hidden=$('#user-popup').classList.toggle('hidden');$('#user-avatar').setAttribute('aria-expanded',String(!hidden))};
  document.addEventListener('click',e=>{const popup=$('#user-popup');if(!popup.classList.contains('hidden')&&!e.target.closest('#user-popup')&&e.target.id!=='user-avatar'){popup.classList.add('hidden');$('#user-avatar').setAttribute('aria-expanded','false')}});
  $('#user-popup').addEventListener('click',e=>{if(e.target.closest('.nav-item')){$('#user-popup').classList.add('hidden');$('#user-avatar').setAttribute('aria-expanded','false')}});
  document.addEventListener('ophir-filter-toggle',event=>{if(event.detail?.key)state.mobileFiltersOpen[event.detail.key]=Boolean(event.detail.open)});
  window.addEventListener('scroll',()=>$('#back-to-top').classList.toggle('hidden',window.scrollY<600),{passive:true});
  $('#back-to-top').onclick=()=>window.scrollTo({top:0,behavior:'smooth'});
  $('#edit-toggle').onclick=toggleEditMode;
  $('#edit-indicator').onclick=()=>setEditMode(false,true);
  $('#edit-panel').onclick=event=>{if(!event.target.closest('#edit-toggle')&&getComputedStyle($('#edit-toggle')).display==='none')toggleEditMode()};
  $$('[data-new-figure]').forEach(button=>button.onclick=()=>openFigureForm());
  setEditMode(state.edit);
  const searchOpen=()=>{openOverlay('search-overlay');setTimeout(()=>$('#global-search-input').focus(),50)};
  $('#global-search-open').onclick=searchOpen;
  document.addEventListener('keydown',e=>{
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();searchOpen()}
    if(e.key==='Escape')$$('.overlay:not(.hidden)').forEach(x=>closeOverlay(x.id));
  });
  let searchTimer;$('#global-search-input').oninput=e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>doSearch(e.target.value),220)};
  $$('.overlay').forEach(o=>o.addEventListener('mousedown',e=>{if(e.target===o)closeOverlay(o.id)}));
  $$('[data-close]').forEach(b=>b.onclick=()=>closeOverlay(b.dataset.close));
  $('#importexport-open').onclick=()=>openImportExport('export');
  wireImportExport();
}

const OAUTH_ERROR_MESSAGES={
  not_configured:'Single Sign-On ist auf diesem Server nicht aktiviert.',
  state_mismatch:'Die Anmeldeanfrage ist abgelaufen oder ungültig. Bitte erneut versuchen.',
  provider_error:'Der Identity Provider hat die Anmeldung abgelehnt oder ist nicht erreichbar.',
  already_linked:'Diese SSO-Identität ist bereits mit einem anderen Konto verknüpft.',
};

async function init(){
  try{
    state.boot=await api('/api/bootstrap');
    const u=state.boot.user,settings=state.boot.settings||{};
    $('#user-name').textContent=u.display_name;$('#user-role').textContent=u.role==='admin'?'Administrator':'Sammler';$('#user-avatar').textContent=initials(u.display_name);
    document.body.classList.toggle('is-admin',u.role==='admin');
    if(settings.sidebarCollapsed)document.body.classList.add('sidebar-collapsed');
    applyAppearance();wireGlobalEvents();paintCounts();
    document.body.dataset.route='dashboard';renderDashboard();
    // Back from a self-service SSO "Verbinden" click in Settings: its outcome as a toast, once.
    const params=new URLSearchParams(location.search);
    if(params.has('linked')){toast('SSO-Verbindung hergestellt');state.boot.user.oauth_linked=true;history.replaceState(null,'',location.pathname)}
    else if(params.has('oauth_error')){toast(OAUTH_ERROR_MESSAGES[params.get('oauth_error')]||'SSO-Verknüpfung fehlgeschlagen.');history.replaceState(null,'',location.pathname)}
    handleImportFragment();
  }catch(error){content.innerHTML=`<div class="empty-state"><b>Ophir Figures konnte nicht geladen werden</b><span>${escapeHtml(error.message)}</span></div>`}
}

init();
