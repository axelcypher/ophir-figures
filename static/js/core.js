// Shared state, small helpers, the API client, dialogs, navigation between views.

const defaultCatalogFilters=()=>({q:'',mode:'all',category:'',manufacturer:'',series:'',character:'',year:'',line:'',scale:'',sort:'release',direction:''});
const defaultCollectionFilters=()=>({q:'',category:'',manufacturer:'',series:'',character:'',year:'',location:'',condition:'',sort:'added',direction:'desc'});
const defaultWatchFilters=()=>({q:'',mode:'all',category:'',manufacturer:'',series:'',sort:'wished',direction:'desc'});

const state={
  boot:null, route:'dashboard', edit:false, view:'grid',
  catalogFilters:defaultCatalogFilters(), collectionFilters:defaultCollectionFilters(), watchFilters:defaultWatchFilters(),
  watchlistId:null, preorderStatus:'open', modalFigure:null, modalTab:'copies', suggestions:null, mobileFiltersOpen:{}, gridFigures:[],
};

const $ = (q, root=document) => root.querySelector(q);
const $$ = (q, root=document) => [...root.querySelectorAll(q)];
const content = $('#content');
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const currencyMoney = (value,currency='EUR') => {
  try{return new Intl.NumberFormat('de-DE',{style:'currency',currency,maximumFractionDigits:currency==='JPY'||currency==='KRW'?0:2}).format(Number(value)||0)}
  catch{return `${Number(value)||0} ${currency}`}
};
const money = value => currencyMoney(value,'EUR');
const moneyOrDash = value => value == null ? '–' : money(value);
// An amount for a form field, as it is typed in German: 159,90 / 22000.
const amountValue = value => value == null || value === '' ? '' : (Number(value) % 1 ? Number(value).toFixed(2) : String(Number(value))).replace('.', ',');
const date = value => value ? new Intl.DateTimeFormat('de-DE',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(value)) : '–';
const MONTH_NAMES=['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
// A release or order date as precise as it is known: "2025", "März 2025", "14.03.2025".
function partialDate(value){
  if(!value)return '';
  const [year,month,day]=String(value).split('-');
  if(day)return `${day.slice(0,2)}.${month}.${year}`;
  if(month)return `${MONTH_NAMES[Number(month)-1]||month} ${year}`;
  return year;
}
const thisMonth=()=>new Date().toISOString().slice(0,7);
const plural=(count,one,many)=>`${count} ${count===1?one:many}`;
const conditionLabel=key=>state.boot?.conditions?.[key]||key;
const statusLabel=key=>state.boot?.statuses?.[key]||key;
const figureThumb=figure=>`/images/figures/${figure.id??figure.figure_id}/thumb${figure.image_version?`?v=${figure.image_version}`:''}`;
const figureImage=figure=>`/images/figures/${figure.id??figure.figure_id}${figure.image_version?`?v=${figure.image_version}`:''}`;

const api = async (url, options={}) => {
  let response;
  try{
    response = await fetch(url,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
  }catch(networkError){
    const error=new Error('Keine Verbindung zum Server');
    error.isNetworkError=true;
    throw error;
  }
  if (response.status===401) { location.href='/login'; const error=new Error('Nicht angemeldet'); error.isAuthError=true; throw error; }
  let data;
  try{data = await response.json()}
  catch(parseError){throw new Error(`Serverfehler (${response.status})`)}
  if (!response.ok){const error=new Error(data.error || 'Anfrage fehlgeschlagen');error.status=response.status;error.data=data;throw error}
  return data;
};
const post = (url,data) => api(url,{method:'POST',body:JSON.stringify(data)});
const patch = (url,data) => api(url,{method:'PATCH',body:JSON.stringify(data)});
const del = url => api(url,{method:'DELETE'});

// A setting saved once its control rests (a slider reports every step); one still waiting when the
// page is left goes out with the unload.
const SETTING_SAVE_DELAY_MS=400;
const pendingSettings=new Map();
function saveSettingSoon(key,value){
  if(state.boot)state.boot.settings[key]=value;
  clearTimeout(pendingSettings.get(key)?.timer);
  const timer=setTimeout(()=>{pendingSettings.delete(key);post('/api/settings',{[key]:value}).catch(()=>{})},SETTING_SAVE_DELAY_MS);
  pendingSettings.set(key,{timer,value});
}
function flushPendingSettings(){
  if(!pendingSettings.size)return;
  const settings={};
  for(const [key,{timer,value}] of pendingSettings){clearTimeout(timer);settings[key]=value}
  pendingSettings.clear();
  fetch('/api/settings',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)}).catch(()=>{});
}
addEventListener('pagehide',flushPendingSettings);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')flushPendingSettings()});

// Debounced search boxes re-render their view; only the most recently started render may put the
// focus and cursor back, so a slow earlier answer never moves the cursor while typing.
const reRenderTokens=new Map();
async function reRenderPreservingFocus(selector,renderFn){
  const myToken=(reRenderTokens.get(selector)||0)+1;
  reRenderTokens.set(selector,myToken);
  const active=document.activeElement;
  const hadFocus=active&&active.matches&&active.matches(selector);
  const selStart=hadFocus?active.selectionStart:null,selEnd=hadFocus?active.selectionEnd:null;
  await renderFn();
  if(reRenderTokens.get(selector)!==myToken)return;
  if(hadFocus){
    const el=$(selector);
    if(el){el.focus();if(selStart!=null)try{el.setSelectionRange(selStart,selEnd)}catch{}}
  }
}

function toast(message, actionLabel, action, key) {
  if(key)$$('.toast',$('#toast-stack')).filter(old=>old.dataset.key===key).forEach(old=>old.remove());
  const node=document.createElement('div'); node.className='toast'; if(key)node.dataset.key=key;
  node.innerHTML=`<span>${escapeHtml(message)}</span>${actionLabel?`<button>${escapeHtml(actionLabel)}</button>`:''}`;
  if(actionLabel) $('button',node).onclick=async()=>{ await action?.(); node.remove(); };
  $('#toast-stack').append(node); setTimeout(()=>node.remove(),actionLabel?8000:5000);
}

function setNav(route) {
  $$('.nav-item[data-route]').forEach(el=>el.classList.toggle('active',el.dataset.route===route));
  $$('.mt-tab[data-route]').forEach(el=>el.classList.toggle('active',el.dataset.route===route));
  $$('.mobile-profile-button[data-route]').forEach(el=>el.classList.toggle('active',el.dataset.route===route));
}

function setEditMode(enabled,announce=false){
  state.edit=Boolean(enabled);
  document.body.classList.toggle('editing',state.edit);
  $('#edit-panel')?.classList.toggle('on',state.edit);
  $('#edit-toggle')?.setAttribute('aria-checked',String(state.edit));
  $('#mobile-edit-toggle')?.classList.toggle('active',state.edit);
  $('#mobile-edit-toggle')?.setAttribute('aria-pressed',String(state.edit));
  if(announce)toast(state.edit?'Schnellbearbeitung an: Plus und Herz direkt auf den Kacheln':'Schnellbearbeitung aus');
}
function toggleEditMode(){setEditMode(!state.edit,true)}

// A view that finishes loading after the user has moved on must not draw over what is on screen.
let renderGeneration=0;
function renderGuard(){const mine=++renderGeneration;return ()=>mine!==renderGeneration}

const TITLES={dashboard:'Übersicht',catalog:'Katalog',collection:'Sammlung',watchlist:'Wunschlisten',preorders:'Vorbestellungen',settings:'Einstellungen',admin:'Admin'};
function routeTo(route, data) {
  renderGeneration++;
  state.mobileFiltersOpen={};
  state.route=route; document.body.dataset.route=route; setNav(route); window.scrollTo({top:0,behavior:'smooth'});
  $('.mobile-topbar-title').textContent=TITLES[route]||'';
  if(route==='dashboard') renderDashboard();
  if(route==='catalog') renderCatalog();
  if(route==='collection') renderCollection();
  if(route==='watchlist') renderWatchlist(data);
  if(route==='preorders') renderPreorders();
  if(route==='settings') renderSettings();
  if(route==='admin') renderAdmin();
}
// Redraws whatever is on screen after a change elsewhere (a dialog saved something).
function refreshCurrentView(){
  if(['dashboard','catalog','collection','watchlist','preorders'].includes(state.route)){
    const y=window.scrollY;
    const result=routeTo(state.route,state.route==='watchlist'?state.watchlistId:undefined);
    requestAnimationFrame(()=>window.scrollTo({top:y}));
    return result;
  }
}
async function refreshCounts(){
  try{
    const boot=await api('/api/bootstrap');
    state.boot.counts=boot.counts;state.boot.watchlists=boot.watchlists;state.boot.imports=boot.imports;
    paintCounts();
  }catch{}
}
function paintCounts(){
  const counts=state.boot.counts||{};
  for(const [key,value] of Object.entries(counts)){
    $$(`[data-count="${key}"]`).forEach(badge=>{badge.textContent=value;badge.classList.toggle('hidden',!value)});
  }
}

function initials(name){return name.split(/\s+/).map(x=>x[0]).slice(0,2).join('').toUpperCase()}

function mountFilterPanel(key,selectors,label='Filter'){
  const targets=selectors.map(selector=>$(selector,content)).filter(Boolean);
  if(!targets.length)return;
  const panel=document.createElement('ophir-filter-panel');
  panel.setAttribute('filter-key',key);
  panel.setAttribute('label',label);
  panel.dataset.mobileFilterShell=key;
  if(state.mobileFiltersOpen[key])panel.setAttribute('open','');
  targets[0].before(panel);
  targets.forEach(target=>{target.classList.add('shared-filter-content');panel.contentElement.append(target)});
}

function statPill(items,{className='',columns=items.length,mobileColumns=Math.min(items.length,2)}={}){
  const safeColumns=Math.max(1,Math.min(8,Number(columns)||items.length||1));
  const safeMobileColumns=Math.max(1,Math.min(8,Number(mobileColumns)||Math.min(safeColumns,2)));
  const classAttribute=className?` class="${escapeHtml(className)}"`:'';
  return `<ophir-stat-pill${classAttribute} columns="${safeColumns}" mobile-columns="${safeMobileColumns}">${items.map(item=>{
    const itemClass=item.className?` class="${escapeHtml(item.className)}"`:'';
    return `<div data-stat${itemClass}><span>${escapeHtml(item.label)}</span><b>${item.value}</b></div>`;
  }).join('')}</ophir-stat-pill>`;
}

function lockScroll(locked){document.documentElement.style.overflow=locked?'hidden':'';document.body.style.overflow=locked?'hidden':''}
function openOverlay(id){$(`#${id}`).classList.remove('hidden');lockScroll(true)}
function closeOverlay(id){
  $(`#${id}`).classList.add('hidden');
  if(!$('.overlay:not(.hidden)')&&!$('.dl-modal-overlay'))lockScroll(false);
  if(id==='figure-modal')state.modalFigure=null;
}

// A dialog over the page: openDialog() returns its element, the caller fills and wires it.
// stack: open over a dialog that is already open instead of replacing it.
function openDialog({id,eyebrow='',title,intro='',body='',stack=false,wide=false}){
  if(!stack)while($('.dl-modal-overlay'))closeDialog();
  const modal=document.createElement('div');
  modal.id=id;modal.className='overlay dl-modal-overlay';
  modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby',`${id}-title`);
  modal.innerHTML=`<div class="dl-modal${wide?' dl-modal-wide':''}"><div class="dl-modal-head"><div>${eyebrow?`<span class="eyebrow">${eyebrow}</span>`:''}<h2 id="${id}-title">${title}</h2>${intro?`<p>${intro}</p>`:''}</div><button class="close-button" type="button" data-dialog-close aria-label="Schließen">×</button></div><div class="dl-modal-body">${body}</div></div>`;
  document.body.append(modal);
  lockScroll(true);
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  modal.onmousedown=event=>{if(event.target===modal)closeDialog()};
  requestAnimationFrame(()=>$('input:not([type=hidden]):not([type=checkbox]),select,textarea',$('.dl-modal-body',modal))?.focus());
  return modal;
}
function closeDialog(){
  const open=$$('.dl-modal-overlay').at(-1);if(!open)return;
  open.remove();
  if(!$('.dl-modal-overlay')&&!$('.overlay:not(.hidden)'))lockScroll(false);
}
// Kept for the settings view, which opened its dialogs under this name.
const openSettingsModal=openDialog,closeSettingsModal=closeDialog;
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('.dl-modal-overlay')){event.stopPropagation();closeDialog()}},true);

// Values of a dialog's fields: every element with data-field, by that name.
function fieldValues(root){
  const values={};
  $$('[data-field]',root).forEach(field=>{values[field.dataset.field]=field.type==='checkbox'?field.checked:field.value});
  return values;
}
const datalist=(id,values=[])=>`<datalist id="${id}">${values.map(value=>`<option value="${escapeHtml(value)}"></option>`).join('')}</datalist>`;
async function loadSuggestions(force=false){
  if(!state.suggestions||force)state.suggestions=await api('/api/figures/suggestions');
  return state.suggestions;
}

// What a search box's text matches, as on the server (ophir_figures/search.py): every word somewhere
// in the fields, spaces/case/accents aside and a letter off allowed; with | ^ $ \ [ ] * + ? { } the
// text as typed or read as a regular expression ("Miku|Rin").
const searchFold=text=>String(text??'').normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase();
const searchWords=text=>searchFold(text).match(/[\p{L}\p{N}_]+/gu)||[];
function searchWithin(word,other,limit){
  if(Math.abs(word.length-other.length)>limit)return false;
  let previous=[...Array(other.length+1).keys()];
  for(let i=1;i<=word.length;i++){
    const current=[i];
    for(let j=1;j<=other.length;j++)current.push(Math.min(previous[j]+1,current[j-1]+1,previous[j-1]+(word[i-1]!==other[j-1])));
    if(Math.min(...current)>limit)return false;
    previous=current;
  }
  return previous[other.length]<=limit;
}
function searchNearMiss(token,words){
  if(token.length<4||/\d/.test(token))return false;
  const limit=token.length<8?1:2;
  return [...words,...words.slice(1).map((word,i)=>words[i]+word)].some(word=>searchWithin(token,word,limit)
    ||[token.length-1,token.length,token.length+1].some(size=>size>0&&size<word.length&&searchWithin(token,word.slice(0,size),limit)));
}
function searchMatcher(query){
  query=query.trim();
  if(/[|^$\\[\]*+?{}]/.test(query)){
    const literal=query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    let pattern;
    try{pattern=new RegExp(query.length<=200?`${literal}|(?:${query})`:literal,'i')}catch{pattern=new RegExp(literal,'i')}
    return fields=>fields.some(text=>text!=null&&pattern.test(String(text)));
  }
  const tokens=[...new Set(searchWords(query))];
  return fields=>{
    const present=fields.filter(text=>text!=null&&text!=='').map(searchWords);
    return tokens.every(token=>present.some(words=>words.join('').includes(token)||searchNearMiss(token,words)));
  };
}

// The quick search (Ctrl+K). An answer that arrives after a newer search started is dropped.
let searchSequence=0,searchController=null;
async function doSearch(q){
  const mine=++searchSequence;searchController?.abort();searchController=null;
  const wrap=$('#search-results');
  if(q.trim().length<2){wrap.innerHTML='<div class="empty-search"><b>Finde jede Figur. Sofort.</b><span>Name, Charakter, Serie, Hersteller oder JAN – in beliebiger Reihenfolge, z.&nbsp;B. „Miku 1/7 Good Smile“. Alternativen mit |: Rem|Ram</span></div>';return}
  const controller=searchController=new AbortController();
  let rows;
  try{rows=await api(`/api/search?q=${encodeURIComponent(q)}`,{signal:controller.signal})}
  catch(error){if(mine!==searchSequence)return;throw error}
  if(mine!==searchSequence)return;
  if(!rows.length){wrap.innerHTML=`<div class="empty-search"><b>Keine Treffer</b><span>Nicht im Katalog? <button type="button" class="link-button" id="search-create">„${escapeHtml(q)}“ neu anlegen</button></span></div>`;
    $('#search-create',wrap).onclick=()=>{closeOverlay('search-overlay');openFigureForm({name:q})};return}
  wrap.innerHTML=rows.map(r=>`<button class="search-result" data-figure="${r.id}"><img class="search-thumb fig-search-thumb" loading="lazy" src="${figureThumb(r)}" alt=""><div><b>${escapeHtml(r.name)}</b><small>${escapeHtml([r.manufacturer,r.series,partialDate(r.release_date)].filter(Boolean).join(' · '))}</small></div><span class="search-price">${r.owned?`<span class="fig-owned-mark">×${r.owned}</span>`:''}${r.preordered?'<span class="fig-pre-mark">VB</span>':''}${r.wished?'♥':''}</span></button>`).join('');
  $$('.search-result',wrap).forEach(el=>el.onclick=()=>{closeOverlay('search-overlay');openFigure(Number(el.dataset.figure))});
}

// Light, dark or what the system uses. The resolved choice is also kept in a cookie: the login
// page and the first paint of the app read it before any settings have loaded.
const systemDark=globalThis.matchMedia?.('(prefers-color-scheme: dark)');
const appearancePreference=()=>['light','dark','auto'].includes(state.boot?.settings?.mobileThemeAppearance)?state.boot.settings.mobileThemeAppearance:'dark';
function applyAppearance(){
  const preference=appearancePreference();
  const light=preference==='light'||(preference==='auto'&&!systemDark?.matches);
  document.body.classList.toggle('mobile-light',light);
  document.cookie=`ophir_figures_theme=${light?'light':'dark'};path=/;max-age=31536000;samesite=lax`;
}
systemDark?.addEventListener?.('change',()=>{if(state.boot&&appearancePreference()==='auto')applyAppearance()});
