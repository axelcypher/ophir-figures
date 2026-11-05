// The public profile (templates/public.html, ophir_figures/public_profile.py): a shared collection
// without signing in. Its own small script -- the app's scripts expect a signed-in user. The
// address says what is shown: #wishlist for the shared wishlist, otherwise the collection.

const view=document.getElementById('content');
const slug=view.dataset.slug;
// The path the app is served under ('' at the root, e.g. /figures behind a proxy), from <html data-root>.
const root=document.documentElement.dataset.root||'';
const base=`${root}/u/${encodeURIComponent(slug)}`;
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number=value=>Number(value||0).toLocaleString('de-DE');
const MONTHS=['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
const partialDate=value=>{if(!value)return '';const [year,month,day]=value.split('-');return day?`${day}.${month}.${year}`:month?`${MONTHS[Number(month)-1]} ${year}`:year};
const filters={q:'',category:'',manufacturer:'',series:''};
let profile=null;

const matches=(figure,query)=>{
  const words=query.toLowerCase().normalize('NFKD').replace(/\p{M}/gu,'').match(/[\p{L}\p{N}]+/gu)||[];
  const text=[figure.name,figure.original_name,figure.characters,figure.series,figure.manufacturer,figure.line,figure.scale].join(' ').toLowerCase().normalize('NFKD').replace(/\p{M}/gu,'');
  return words.every(word=>text.includes(word));
};

function tile(figure){
  return `<article class="fig-tile${figure.owned?' owned':''}" tabindex="0" data-figure="${figure.id}">
    <div class="fig-art"><img loading="lazy" decoding="async" src="${base}/images/${figure.id}${figure.image_version?`?v=${esc(figure.image_version)}`:''}" alt="">
      ${figure.owned>1?`<div class="fig-marks"><span class="fig-mark owned">×${figure.owned}</span></div>`:''}</div>
    <div class="fig-meta"><b title="${esc(figure.name)}">${esc(figure.name)}</b><small>${esc([figure.manufacturer,partialDate(figure.release_date)].filter(Boolean).join(' · '))||'&nbsp;'}</small></div>
  </article>`;
}

function showFigure(figure){
  const facts=[['Serie',figure.series],['Charaktere',figure.characters],['Hersteller',figure.manufacturer],['Kategorie',figure.category],['Linie',figure.line],['Maßstab',figure.scale],['Edition',figure.edition],['Erscheinung',partialDate(figure.release_date)]].filter(([,value])=>value);
  const overlay=document.createElement('div');
  overlay.className='overlay';overlay.id='public-figure';
  overlay.innerHTML=`<div class="fig-dialog" role="dialog" aria-modal="true"><button type="button" class="close-button fig-dialog-close" aria-label="Schließen">×</button>
    <div class="fig-dialog-media"><img src="${base}/images/${figure.id}?size=full${figure.image_version?`&v=${esc(figure.image_version)}`:''}" alt="${esc(figure.name)}"></div>
    <div class="fig-dialog-main"><span class="eyebrow">${esc([figure.category,figure.scale].filter(Boolean).join(' · ').toUpperCase())}</span><h2>${esc(figure.name)}</h2>${figure.original_name?`<p class="fig-original">${esc(figure.original_name)}</p>`:''}
      <dl class="fig-facts">${facts.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl></div></div>`;
  const close=()=>{overlay.remove();document.body.style.overflow=''};
  overlay.onmousedown=event=>{if(event.target===overlay)close()};
  overlay.querySelector('.close-button').onclick=close;
  document.addEventListener('keydown',function onKey(event){if(event.key==='Escape'){close();document.removeEventListener('keydown',onKey)}});
  document.body.append(overlay);document.body.style.overflow='hidden';
}

function render(){
  const wishlist=location.hash==='#wishlist'&&profile.wishlist;
  const all=wishlist?profile.wishlist:profile.collection;
  let shown=all.filter(figure=>['category','manufacturer','series'].every(key=>!filters[key]||figure[key]===filters[key]));
  if(filters.q.trim())shown=shown.filter(figure=>matches(figure,filters.q));
  const select=(key,label)=>{
    const values=[...new Set(all.map(figure=>figure[key]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'de'));
    return values.length>1?`<label class="fig-filter"><span>${label}</span><select class="select-control" data-filter="${key}"><option value="">Alle</option>${values.map(value=>`<option ${filters[key]===value?'selected':''}>${esc(value)}</option>`).join('')}</select></label>`:'';
  };
  view.innerHTML=`<section class="public-head"><div><span class="eyebrow">ÖFFENTLICHE SAMMLUNG</span><h1>${esc(profile.name)}</h1>
      <p>${number(profile.stats.figures)} Figuren · ${number(profile.stats.copies)} Exemplare</p></div></section>
    ${profile.wishlist?`<nav class="segmented public-games" aria-label="Ansicht"><button type="button" data-view="" class="${wishlist?'':'active'}">Sammlung</button><button type="button" data-view="#wishlist" class="${wishlist?'active':''}">Wunschliste <small>${profile.wishlist.length}</small></button></nav>`:''}
    <div class="fig-toolbar"><div class="fig-toolbar-row">
      <label class="fig-search"><span aria-hidden="true">⌕</span><input type="search" id="public-search" value="${esc(filters.q)}" placeholder="Name, Serie, Hersteller …"></label>
      ${select('category','Kategorie')}${select('manufacturer','Hersteller')}${select('series','Serie')}
    </div></div>
    ${shown.length?`<div class="fig-grid">${shown.map(tile).join('')}</div>`:`<div class="empty-state"><b>${all.length?'Keine Figur passt zur Suche':'Hier ist noch nichts'}</b></div>`}`;
  view.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>{history.replaceState(null,'',button.dataset.view||location.pathname);render()});
  view.querySelectorAll('[data-filter]').forEach(select=>select.onchange=()=>{filters[select.dataset.filter]=select.value;render()});
  const search=view.querySelector('#public-search');
  let timer;search.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{filters.q=search.value;render();const field=view.querySelector('#public-search');field.focus();field.setSelectionRange(field.value.length,field.value.length)},250)};
  const byId=new Map(all.map(figure=>[figure.id,figure]));
  view.querySelectorAll('[data-figure]').forEach(element=>{
    element.onclick=()=>showFigure(byId.get(Number(element.dataset.figure)));
    element.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();element.click()}};
  });
}

fetch(`${root}/api/public/${encodeURIComponent(slug)}`).then(async response=>{
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||`Fehler ${response.status}`);
  profile=data;render();
}).catch(error=>{view.innerHTML=`<div class="empty-state"><b>Die Sammlung konnte nicht geladen werden</b><span>${esc(error.message)}</span></div>`});
addEventListener('hashchange',()=>profile&&render());
