// What every figure view shares: tiles and grids, the filter bar, the figure dialog with its tabs,
// and the forms for a figure (with the link import), a copy, a preorder and wishlist entries.

// ---- Tiles and grids --------------------------------------------------------------------------

const GRID_PAGE=180;

function figureSubtitle(figure){
  return [figure.manufacturer,partialDate(figure.release_date)].filter(Boolean).join(' · ');
}

function figureTile(figure,{note='',value=null,badge=''}={}){
  const marks=[
    figure.owned?`<span class="fig-mark owned" title="In deiner Sammlung">×${figure.owned}</span>`:'',
    figure.preordered?`<span class="fig-mark preordered" title="Vorbestellt">VB</span>`:'',
    badge,
  ].join('');
  const shownValue=value!==null?value:figure.market_value;
  return `<article class="fig-tile${figure.owned?' owned':''}" data-figure="${figure.id}" tabindex="0" aria-label="${escapeHtml(figure.name)}">
    <div class="fig-art"><img loading="lazy" decoding="async" src="${figureThumb(figure)}" alt="">
      <div class="fig-marks">${marks}</div>
      <button type="button" class="fig-heart${figure.wished?' active':''}" data-wish="${figure.id}" aria-pressed="${figure.wished?'true':'false'}" title="${figure.wished?'Auf der Wunschliste':'Auf die Wunschliste'}"><svg viewBox="0 0 24 24"><path d="M12 20.5s-7.5-4.6-9.8-9A5.4 5.4 0 0 1 12 6a5.4 5.4 0 0 1 9.8 5.5c-2.3 4.4-9.8 9-9.8 9Z"/></svg></button>
      <button type="button" class="fig-plus" data-quick-add="${figure.id}" title="Ein Exemplar zur Sammlung hinzufügen">＋</button>
    </div>
    <div class="fig-meta">
      <b title="${escapeHtml(figure.name)}">${escapeHtml(figure.name)}</b>
      <small>${escapeHtml(figureSubtitle(figure))||'&nbsp;'}</small>
      ${note?`<span class="fig-note">${note}</span>`:''}
      ${shownValue!=null?`<span class="fig-value">${money(shownValue)}</span>`:''}
    </div>
  </article>`;
}

// Draws a grid in pages (a catalogue can hold thousands of figures); tile() makes one tile.
function renderFigureGrid(container,figures,{tile=figure=>figureTile(figure),empty='<div class="empty-state"><b>Keine Figuren</b><span>Ändere die Filter oder lege eine Figur an.</span></div>'}={}){
  state.gridFigures=figures;
  if(!figures.length){container.innerHTML=empty;return}
  let shown=0;
  container.innerHTML='<div class="fig-grid"></div><div class="fig-grid-more"></div>';
  const grid=$('.fig-grid',container),more=$('.fig-grid-more',container);
  const page=()=>{
    grid.insertAdjacentHTML('beforeend',figures.slice(shown,shown+GRID_PAGE).map(tile).join(''));
    shown=Math.min(figures.length,shown+GRID_PAGE);
    more.innerHTML=shown<figures.length?`<button type="button" class="secondary-button">Weitere ${Math.min(GRID_PAGE,figures.length-shown)} von ${figures.length-shown} anzeigen</button>`:'';
    const button=$('button',more);
    if(button){
      button.onclick=page;
      // Scrolling to the end loads the next page by itself.
      const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){observer.disconnect();page()}},{rootMargin:'600px'});
      observer.observe(button);
    }
  };
  page();
  wireFigureGrid(grid);
}

function wireFigureGrid(grid){
  grid.addEventListener('click',async event=>{
    const wish=event.target.closest('[data-wish]');
    if(wish){event.stopPropagation();await toggleWish(Number(wish.dataset.wish),wish);return}
    const add=event.target.closest('[data-quick-add]');
    if(add){event.stopPropagation();await quickAddCopy(Number(add.dataset.quickAdd));return}
    const tile=event.target.closest('[data-figure]');
    if(tile)openFigure(Number(tile.dataset.figure));
  });
  grid.addEventListener('keydown',event=>{
    if((event.key==='Enter'||event.key===' ')&&event.target.matches('.fig-tile')){event.preventDefault();openFigure(Number(event.target.dataset.figure))}
  });
}

function defaultListId(){return state.boot.watchlists.find(list=>list.is_default)?.id}

async function toggleWish(figureId,button){
  const listId=defaultListId(),active=button?.classList.contains('active');
  try{
    if(active){
      const result=await del(`/api/watchlists/${listId}/figures/${figureId}`);
      state.boot.watchlists=result.lists;
      toast('Von der Wunschliste genommen','Rückgängig',async()=>{await post(`/api/watchlists/${listId}/figures`,{figure_id:figureId,...result.removed});refreshCounts();refreshCurrentView()},'wish');
    }else{
      const result=await post(`/api/watchlists/${listId}/figures`,{figure_id:figureId});
      state.boot.watchlists=result.lists;
      toast('Auf die Wunschliste gesetzt','Zielpreis …',()=>openWishDialog(figureId),'wish');
    }
    if(button){button.classList.toggle('active',!active);button.setAttribute('aria-pressed',String(!active))}
    const figure=state.gridFigures.find(item=>item.id===figureId);if(figure)figure.wished=!active;
    refreshCounts();
    if(state.route==='watchlist')renderWatchlist(state.watchlistId);
  }catch(error){toast(error.message)}
}

async function quickAddCopy(figureId){
  try{
    const entry=await post('/api/collection',{figure_id:figureId,quantity:1});
    toast('Ein Exemplar hinzugefügt','Rückgängig',async()=>{await del(`/api/collection/${entry.id}`);refreshCounts();refreshCurrentView()},'quick-add');
    refreshCounts();refreshCurrentView();
  }catch(error){toast(error.message)}
}

// ---- The filter bar ---------------------------------------------------------------------------

const SORT_LABELS={release:'Erscheinung',name:'Name',series:'Franchise',brand:'Marke',manufacturer:'Hersteller',line:'Linie',added:'Hinzugefügt',value:'Marktwert',purchased:'Kaufdatum',spent:'Kaufpreis',collection_value:'Wert',wished:'Gewünscht seit'};
const FACET_LABELS={series:'Franchise',character:'Charakter',brand:'Marke',manufacturer:'Hersteller',line:'Linie',category:'Kategorie',scale:'Maßstab',year:'Jahr',location:'Aufbewahrung'};

// grouping: the view's state.grouping entry. While it shows groups, the bar sorts the groups and
// leaves out the filter by the field they are grouped by; with a group open, that filter is the group.
function filterBar({key,filters,facets={},modes=null,sorts=[],extraFacets=[],extra='',grouping=null}){
  const overview=Boolean(grouping?.by&&!grouping.open),locked=grouping?.open?.by;
  const facetKeys=[...['series','character','brand','manufacturer','line','category'],...extraFacets,'year'].filter(name=>facets[name]&&!(overview&&name===grouping.by));
  const select=name=>{
    const options=facets[name]||[];
    if(!options.length&&!filters[name])return '';
    const none=filters[name]===NONE_VALUE?`<option value="${NONE_VALUE}" selected>Ohne ${FACET_LABELS[name]||name}</option>`:'';
    return `<label class="fig-filter"><span>${FACET_LABELS[name]||name}</span><select class="select-control" data-filter="${name}"><option value="">Alle</option>${none}${options.map(([value,count])=>`<option value="${escapeHtml(value)}" ${filters[name]===value?'selected':''}>${escapeHtml(value)} (${count})</option>`).join('')}</select></label>`;
  };
  return `<div class="fig-toolbar" data-filter-bar="${key}">
    <div class="fig-toolbar-row">
      <label class="fig-search"><span aria-hidden="true">⌕</span><input type="search" data-filter="q" value="${escapeHtml(filters.q||'')}" placeholder="Name, Charakter, Franchise, JAN … (Rem|Ram)" autocomplete="off"></label>
      ${modes?`<div class="segmented fig-modes">${modes.map(([value,label])=>`<button type="button" data-mode="${value}" class="${(filters.mode||'all')===value?'active':''}">${label}</button>`).join('')}</div>`:''}
      ${extra}
    </div>
    <div class="fig-toolbar-row fig-filter-row">
      ${facetKeys.map(select).join('')}
      ${overview?`<label class="fig-filter"><span>Gruppen sortieren</span><select class="select-control" data-group-sort>${Object.entries(GROUP_SORT_LABELS).map(([value,label])=>`<option value="${value}" ${grouping.sort===value?'selected':''}>${label}</option>`).join('')}</select></label>`
        :`<label class="fig-filter"><span>Sortierung</span><select class="select-control" data-filter="sort">${sorts.map(value=>`<option value="${value}" ${filters.sort===value?'selected':''}>${SORT_LABELS[value]||value}</option>`).join('')}</select></label>
      <button type="button" class="icon-button fig-direction" data-direction title="Reihenfolge umkehren" aria-label="Reihenfolge umkehren">${(filters.direction||defaultDirection(filters.sort))==='asc'?'↑':'↓'}</button>`}
      ${Object.entries(filters).some(([name,value])=>value&&!['sort','direction','mode',locked].includes(name))?'<button type="button" class="link-button" data-filter-reset>Filter zurücksetzen</button>':''}
    </div>
  </div>`;
}
const defaultDirection=sort=>['name','series','brand','manufacturer','line'].includes(sort)?'asc':'desc';

// Wires a filter bar: every change updates `filters` and calls render(); typing waits for a pause.
function wireFilterBar(root,filters,render,reset){
  const bar=$('[data-filter-bar]',root);if(!bar)return;
  let timer;
  $$('[data-filter]',bar).forEach(control=>{
    const apply=()=>{filters[control.dataset.filter]=control.value;if(control.dataset.filter==='sort')filters.direction='';render()};
    if(control.dataset.filter==='q')control.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>reRenderPreservingFocus('[data-filter="q"]',async()=>{filters.q=control.value;await render()}),250)};
    else control.onchange=apply;
  });
  $$('[data-mode]',bar).forEach(button=>button.onclick=()=>{filters.mode=button.dataset.mode;render()});
  $('[data-direction]',bar)?.addEventListener('click',()=>{filters.direction=(filters.direction||defaultDirection(filters.sort))==='asc'?'desc':'asc';render()});
  $('[data-filter-reset]',bar)?.addEventListener('click',()=>{reset();render()});
}
const filterQuery=filters=>new URLSearchParams(Object.entries(filters).filter(([,value])=>value!==''&&value!=null)).toString();

// ---- Groups: a grid's figures side by side by franchise, brand, manufacturer or line ---------

const GROUPINGS=[['series','Franchise','Franchises'],['brand','Marke','Marken'],['manufacturer','Hersteller','Hersteller'],['line','Linie','Linien']];
const GROUP_SORT_LABELS={name:'Name',count:'Anzahl Figuren',owned:'Anteil in der Sammlung',value:'Wert',release:'Neueste Erscheinung'};
// A filter value for the figures without a value in that field (figures.py NONE_VALUE).
const NONE_VALUE='__none__';
const groupingLabel=(by,many=false)=>GROUPINGS.find(([key])=>key===by)?.[many?2:1]||'';
const groupName=(by,name)=>name||`Ohne ${groupingLabel(by)}`;

// The kind each grid was last shown in comes back with the user's settings.
function restoreGroupings(saved){
  if(!saved||typeof saved!=='object')return;
  for(const [view,by] of Object.entries(saved)){
    if(state.grouping[view]&&(by===''||GROUPINGS.some(([key])=>key===by)))state.grouping[view].by=by;
  }
}

// What a grid asks the server for: its filters and, while it shows groups, their kind and order.
function gridQuery(filters,grouping){
  const query=filterQuery(filters);
  return grouping.by&&!grouping.open?`${query}${query?'&':''}group=${grouping.by}&group_sort=${grouping.sort}`:query;
}

// A filter changed in the bar may have moved off the open group: the select of the grouped field
// then picks another group, or with "Alle" goes back to the groups.
function syncOpenGroup(filters,grouping){
  const open=grouping.open;
  if(!open)return;
  const value=filters[open.by]||'';
  if(value===(open.name||NONE_VALUE))return;
  grouping.open=value?{by:open.by,name:value===NONE_VALUE?'':value}:null;
}

function groupSwitch(view){
  const grouping=state.grouping[view];
  const button=(key,label)=>`<button type="button" role="tab" aria-selected="${grouping.by===key}" data-group-by="${key}" class="${grouping.by===key?'active':''}">${label}</button>`;
  return `<div class="segmented fig-group-switch" role="tablist" aria-label="Anzeigen als" data-scroll-x>${button('','Figuren')}${GROUPINGS.map(([key,label])=>button(key,label)).join('')}</div>`;
}

// Wires the switch, the group sort and the way back. Leaving an open group drops its filter.
function wireGroups(root,view,filters,render){
  const grouping=state.grouping[view];
  const close=()=>{if(grouping.open){filters[grouping.open.by]='';grouping.open=null}};
  $$('[data-group-by]',root).forEach(button=>button.onclick=()=>{
    close();grouping.by=button.dataset.groupBy;
    saveSettingSoon('groupings',Object.fromEntries(Object.entries(state.grouping).map(([key,value])=>[key,value.by])));
    render();
  });
  $('[data-group-sort]',root)?.addEventListener('change',event=>{grouping.sort=event.target.value;render()});
  $('[data-group-back]',root)?.addEventListener('click',()=>{close();render()});
}

function openGroup(view,filters,name,render){
  const grouping=state.grouping[view];
  grouping.open={by:grouping.by,name};
  filters[grouping.by]=name||NONE_VALUE;
  render();
  window.scrollTo({top:0});
}

// The head over an open group's figures: the way back to the groups, the group and its numbers;
// detail is one more line (an open line's preset), actions buttons beside it.
function groupHead(view,{count,owned=null,detail='',actions=''}){
  const {by,open}=state.grouping[view];
  const back=`Zurück zu allen ${groupingLabel(by,true)}`;
  return `<div class="fig-group-head">
    <button type="button" class="icon-button fig-group-back" data-group-back title="${back}" aria-label="${back}">←</button>
    <div class="fig-group-title"><span class="eyebrow">${escapeHtml(groupingLabel(by).toUpperCase())}</span><h2>${escapeHtml(groupName(by,open.name))}</h2>
      <small>${[plural(count,'Figur','Figuren'),owned!=null?`${owned} in der Sammlung`:''].filter(Boolean).join(' · ')}</small>
      ${detail?`<small class="fig-group-detail">${escapeHtml(detail)}</small>`:''}</div>
    ${actions?`<div class="fig-group-actions">${actions}</div>`:''}
  </div>`;
}

// One group: up to four of its figures as a mosaic, its name and numbers. stats(group) gives the
// lines under the name and, optionally, a share (0 to 1) for the bar.
function groupTile(by,group,stats){
  const {lines,share=null}=stats(group,by);
  const name=groupName(by,group.name);
  const samples=group.samples.length?group.samples:[null];
  return `<article class="fig-group-tile${group.name?'':' fig-group-none'}" data-group="${escapeHtml(group.name)}" tabindex="0" role="button" aria-label="${escapeHtml(name)} öffnen">
    <div class="fig-group-art" data-count="${samples.length}">${samples.map(sample=>sample?`<img loading="lazy" decoding="async" src="${figureThumb(sample)}" alt="">`:'<span></span>').join('')}</div>
    <div class="fig-group-meta">
      <b title="${escapeHtml(name)}">${escapeHtml(name)}</b>
      ${lines.filter(Boolean).map(line=>`<small>${line}</small>`).join('')}
      ${share!=null?`<span class="fig-group-share" title="${Math.round(share*100)} % in der Sammlung"><i style="--share:${Math.round(share*100)}%"></i></span>`:''}
    </div>
  </article>`;
}

const GROUP_MISSING={series:'eine Franchise',brand:'eine Marke',manufacturer:'einen Hersteller',line:'eine Linie'};

function renderGroupGrid(container,view,groups,{stats,empty,onOpen}){
  const by=state.grouping[view].by;
  if(!groups.length){container.innerHTML=empty;return}
  const unnamed=groups.length===1&&!groups[0].name;
  container.innerHTML=`${unnamed?`<div class="fig-hint"><b>Noch keine dieser Figuren hat ${GROUP_MISSING[by]}.</b><span>Trag sie im Formular der Figur ein${['brand','manufacturer'].includes(by)?' – für ganze Linien auf einmal mit einer Linien-Vorlage':''}.</span></div>`:''}
    <div class="fig-group-grid">${groups.map(group=>groupTile(by,group,stats)).join('')}</div>`;
  const grid=$('.fig-group-grid',container);
  grid.addEventListener('click',event=>{const tile=event.target.closest('[data-group]');if(tile)onOpen(tile.dataset.group)});
  grid.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-group]')){event.preventDefault();onOpen(event.target.dataset.group)}});
}

// ---- The figure dialog ------------------------------------------------------------------------

async function openFigure(figureId,tab){
  if(tab)state.modalTab=tab;
  let figure;
  try{figure=await api(`/api/figures/${figureId}`)}catch(error){toast(error.message);return}
  state.modalFigure=figure;
  paintFigure();
  openOverlay('figure-modal');
}

async function reloadFigure(){
  if(!state.modalFigure)return;
  try{state.modalFigure=await api(`/api/figures/${state.modalFigure.id}`);paintFigure()}catch(error){toast(error.message)}
}

const FIGURE_TABS=[['copies','Exemplare'],['preorders','Vorbestellungen'],['value','Wert'],['lists','Wunschlisten'],['info','Info']];

function factRow(label,value){return value?`<div><dt>${label}</dt><dd>${value}</dd></div>`:''}

function paintFigure(){
  const figure=state.modalFigure,dialog=$('#figure-dialog');
  if(!figure)return;
  const openPreorders=figure.preorders.filter(item=>['ordered','paid','shipped'].includes(item.status));
  const chips=[
    figure.owned?`<span class="fig-chip owned">${figure.owned}× in der Sammlung</span>`:'',
    openPreorders.length?`<span class="fig-chip preordered">Vorbestellt · ${statusLabel(openPreorders[0].status)}</span>`:'',
    figure.wished?'<span class="fig-chip wished">♥ Wunschliste</span>':'',
    figure.market_value!=null?`<span class="fig-chip">Marktwert ${money(figure.market_value)}</span>`:'',
  ].join('');
  const tabs=FIGURE_TABS.map(([key,label])=>{
    const count={copies:figure.entries.length,preorders:figure.preorders.length,value:figure.prices.length,lists:figure.lists.length}[key];
    return `<button type="button" data-figure-tab="${key}" class="${state.modalTab===key?'active':''}">${label}${count?` <small>${count}</small>`:''}</button>`;
  }).join('');
  dialog.innerHTML=`<button type="button" class="close-button fig-dialog-close" data-close="figure-modal" aria-label="Schließen">×</button>
    <div class="fig-dialog-media">${figure.has_image?`<a href="${figureImage(figure)}" target="_blank" rel="noopener" title="Bild in voller Größe"><img src="${figureImage(figure)}" alt="${escapeHtml(figure.name)}"></a>`:`<img src="${figureImage(figure)}" alt="">`}
      <div class="fig-media-actions"><button type="button" class="secondary-button" data-figure-action="image">${figure.has_image?'Bild ändern':'Bild hinzufügen'}</button></div>
    </div>
    <div class="fig-dialog-main">
      <span class="eyebrow">${escapeHtml([figure.category,figure.line,figure.scale].filter(Boolean).join(' · ').toUpperCase()||'FIGUR')}</span>
      <h2>${escapeHtml(figure.name)}</h2>
      ${figure.original_name?`<p class="fig-original">${escapeHtml(figure.original_name)}</p>`:''}
      ${chips?`<div class="fig-chips">${chips}</div>`:''}
      <div class="fig-actions">
        <button type="button" class="primary-button" data-figure-action="copy">＋ Exemplar</button>
        <button type="button" class="secondary-button" data-figure-action="preorder">Vorbestellen</button>
        <button type="button" class="secondary-button${figure.wished?' active':''}" data-figure-action="wish">${figure.wished?'♥ Gewünscht':'♡ Wunschliste'}</button>
        <button type="button" class="secondary-button" data-figure-action="edit">Bearbeiten</button>
      </div>
      <dl class="fig-facts">
        ${factRow('Franchise',escapeHtml(figure.series))}
        ${factRow('Charaktere',escapeHtml(figure.characters))}
        ${factRow('Hersteller',escapeHtml(figure.manufacturer))}
        ${factRow('Marke',escapeHtml(figure.brand))}
        ${factRow('Erscheinung',escapeHtml(partialDate(figure.release_date)))}
        ${factRow('Edition',escapeHtml(figure.edition))}
        ${factRow('Originalpreis',figure.msrp!=null?escapeHtml(currencyMoney(figure.msrp,figure.msrp_currency)):'')}
        ${factRow('Höhe',figure.height_mm?`${figure.height_mm} mm`:'')}
        ${factRow('Sculptor',escapeHtml(figure.sculptor))}
        ${factRow('Material',escapeHtml(figure.material))}
        ${factRow('JAN',escapeHtml(figure.jan))}
      </dl>
      <div class="segmented fig-tabs" role="tablist">${tabs}</div>
      <div class="fig-tab-body" id="figure-tab-body">${figureTabHtml(figure)}</div>
    </div>`;
  $$('[data-close="figure-modal"]',dialog).forEach(button=>button.onclick=()=>closeOverlay('figure-modal'));
  $$('[data-figure-tab]',dialog).forEach(button=>button.onclick=()=>{state.modalTab=button.dataset.figureTab;paintFigure()});
  $$('[data-figure-action]',dialog).forEach(button=>button.onclick=()=>figureAction(button.dataset.figureAction));
  wireFigureTab(figure);
}

function figureAction(action){
  const figure=state.modalFigure;
  if(action==='copy')openEntryDialog(figure);
  if(action==='preorder')openPreorderDialog(figure);
  if(action==='wish')openWishDialog(figure.id);
  if(action==='edit')openFigureForm(figure,{figureId:figure.id});
  if(action==='image')openImageDialog(figure);
}

function entryLine(entry){
  return [conditionLabel(entry.condition),entry.purchase_price!=null?`${money(entry.purchase_price)}${entry.quantity>1?' je Stück':''}`:'',entry.shop,partialDate(entry.purchased_at),entry.location&&`📍 ${entry.location}`].filter(Boolean).map(escapeHtml).join(' · ');
}

function preorderLine(item){
  const parts=[item.shop,item.ordered_at&&`bestellt ${partialDate(item.ordered_at)}`,item.expected_release&&`erwartet ${partialDate(item.expected_release)}`];
  return parts.filter(Boolean).map(escapeHtml).join(' · ');
}

function figureTabHtml(figure){
  const tab=state.modalTab;
  if(tab==='copies'){
    if(!figure.entries.length)return `<p class="muted">Du hast diese Figur noch nicht in deiner Sammlung.</p><button type="button" class="secondary-button" data-figure-action-inline="copy">＋ Exemplar hinzufügen</button>`;
    return `<div class="fig-rows">${figure.entries.map(entry=>`<div class="fig-row"><b>${entry.quantity}×</b><span><span>${entryLine(entry)}</span>${entry.notes?`<small>${escapeHtml(entry.notes)}</small>`:''}${entry.preorder_id?'<small>aus einer Vorbestellung</small>':''}</span><span class="fig-row-actions"><button type="button" class="icon-button" data-edit-entry="${entry.id}" title="Bearbeiten">✎</button><button type="button" class="icon-button" data-delete-entry="${entry.id}" title="Entfernen">✕</button></span></div>`).join('')}</div>
      <button type="button" class="secondary-button" data-figure-action-inline="copy">＋ Weiteres Exemplar</button>`;
  }
  if(tab==='preorders'){
    if(!figure.preorders.length)return `<p class="muted">Keine Vorbestellung für diese Figur.</p><button type="button" class="secondary-button" data-figure-action-inline="preorder">Vorbestellen</button>`;
    return `<div class="fig-rows">${figure.preorders.map(item=>`<div class="fig-row"><span class="status-pill status-${item.status}">${escapeHtml(statusLabel(item.status))}</span><span><span>${preorderLine(item)}</span><small>${item.total!=null?`${money(item.total)}`:'Preis offen'}${item.outstanding?` · noch ${money(item.outstanding)} offen`:''}${item.delays?` · ${item.delays}× verschoben`:''}</small></span><span class="fig-row-actions"><button type="button" class="icon-button" data-edit-preorder="${item.id}" title="Bearbeiten">✎</button></span></div>`).join('')}</div>
      <button type="button" class="secondary-button" data-figure-action-inline="preorder">Weitere Vorbestellung</button>`;
  }
  if(tab==='value'){
    return `<div class="fig-value-head"><div><span class="eyebrow">MARKTWERT</span><b>${moneyOrDash(figure.market_value)}</b></div><small class="muted">Gemeinsam für alle Konten. Ohne Marktwert zählt in deiner Sammlung der Kaufpreis.</small></div>
      ${priceHistoryHtml(figure.prices)}
      <div class="fig-inline-form"><input class="dl-control" id="price-amount" inputmode="decimal" placeholder="Wert in €"><input class="dl-control" id="price-note" placeholder="Quelle/Notiz (optional)"><button type="button" class="primary-button" id="price-add">Eintragen</button></div>
      ${figure.prices.length?`<div class="fig-rows">${figure.prices.map(price=>`<div class="fig-row"><b>${money(price.amount)}</b><span><span>${date(price.observed_at)}${price.author?` · ${escapeHtml(price.author)}`:''}${price.source==='import'?' · aus Link-Import':''}</span>${price.note?`<small>${escapeHtml(price.note)}</small>`:''}</span><span class="fig-row-actions"><button type="button" class="icon-button" data-delete-price="${price.id}" title="Wert löschen">✕</button></span></div>`).join('')}</div>`:''}`;
  }
  if(tab==='lists'){
    const lists=state.boot.watchlists;
    const memberships=new Map(figure.lists.map(item=>[item.list_id,item]));
    return `<div class="fig-rows">${lists.map(list=>{const entry=memberships.get(list.id);return `<div class="fig-row fig-list-row"><label class="fig-list-toggle"><input type="checkbox" data-list-toggle="${list.id}" ${entry?'checked':''}><b>${escapeHtml(list.name)}</b></label>${entry?`<span class="fig-list-fields"><input class="dl-control" data-list-target="${list.id}" inputmode="decimal" placeholder="Zielpreis €" value="${amountValue(entry.target_price)}"><input class="dl-control" data-list-note="${list.id}" placeholder="Notiz" value="${escapeHtml(entry.note)}"></span>`:'<span class="muted">nicht auf der Liste</span>'}</div>`}).join('')}</div>
      <p class="muted">Ein Zielpreis markiert die Figur auf der Liste, sobald ihr Marktwert darunter fällt.</p>`;
  }
  const attributes=Object.entries(figure.attributes||{});
  return `${figure.description?`<p class="fig-description">${escapeHtml(figure.description)}</p>`:'<p class="muted">Keine Beschreibung.</p>'}
    <dl class="fig-facts">
      ${factRow('Quelle',figure.source_url?`<a href="${escapeHtml(figure.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(new URL(figure.source_url).hostname)}</a>`:'')}
      ${factRow('Angelegt',`${date(figure.created_at)}${figure.created_by_name?` von ${escapeHtml(figure.created_by_name)}`:''}`)}
      ${factRow('Sammler',figure.owners?plural(figure.owners,'Konto hat sie','Konten haben sie'):'')}
      ${attributes.map(([key,value])=>factRow(escapeHtml(key),escapeHtml(value))).join('')}
    </dl>
    ${figure.can_delete?'<button type="button" class="secondary-button danger" id="figure-delete">Aus dem Katalog löschen</button>':''}`;
}

function wireFigureTab(figure){
  const body=$('#figure-tab-body');if(!body)return;
  $$('[data-figure-action-inline]',body).forEach(button=>button.onclick=()=>figureAction(button.dataset.figureActionInline));
  $$('[data-edit-entry]',body).forEach(button=>button.onclick=()=>openEntryDialog(figure,figure.entries.find(entry=>entry.id===Number(button.dataset.editEntry))));
  $$('[data-delete-entry]',body).forEach(button=>button.onclick=async()=>{
    try{
      const {deleted}=await del(`/api/collection/${button.dataset.deleteEntry}`);
      toast('Exemplar entfernt','Rückgängig',async()=>{const {id,user_id,created_at,updated_at,preorder_id,...fields}=deleted;await post('/api/collection',fields);afterChange()});
      afterChange();
    }catch(error){toast(error.message)}
  });
  $$('[data-edit-preorder]',body).forEach(button=>button.onclick=()=>openPreorderDialog(figure,figure.preorders.find(item=>item.id===Number(button.dataset.editPreorder))));
  $('#price-add',body)?.addEventListener('click',async()=>{
    try{await post(`/api/figures/${figure.id}/prices`,{amount:$('#price-amount',body).value,note:$('#price-note',body).value});toast('Marktwert eingetragen');afterChange()}
    catch(error){toast(error.message)}
  });
  $('#price-amount',body)?.addEventListener('keydown',event=>{if(event.key==='Enter')$('#price-add',body).click()});
  $$('[data-delete-price]',body).forEach(button=>button.onclick=async()=>{
    try{await del(`/api/figures/${figure.id}/prices/${button.dataset.deletePrice}`);afterChange()}catch(error){toast(error.message)}
  });
  $$('[data-list-toggle]',body).forEach(box=>box.onchange=async()=>{
    const listId=box.dataset.listToggle;
    try{
      const result=box.checked?await post(`/api/watchlists/${listId}/figures`,{figure_id:figure.id}):await del(`/api/watchlists/${listId}/figures/${figure.id}`);
      state.boot.watchlists=result.lists;afterChange();
    }catch(error){toast(error.message)}
  });
  const saveEntry=async listId=>{
    try{await patch(`/api/watchlists/${listId}/figures/${figure.id}`,{target_price:$(`[data-list-target="${listId}"]`,body).value,note:$(`[data-list-note="${listId}"]`,body).value});toast('Gespeichert',null,null,'list-entry')}
    catch(error){toast(error.message)}
  };
  $$('[data-list-target],[data-list-note]',body).forEach(input=>input.onchange=()=>saveEntry(input.dataset.listTarget||input.dataset.listNote));
  $('#figure-delete',body)?.addEventListener('click',async()=>{
    if(!confirm(`„${figure.name}“ endgültig aus dem Katalog löschen?`))return;
    try{await del(`/api/figures/${figure.id}`);closeOverlay('figure-modal');toast('Aus dem Katalog gelöscht');refreshCounts();refreshCurrentView()}
    catch(error){toast(error.message)}
  });
}

// After any change made from a dialog: the open figure, the counts and the view behind it.
function afterChange(){
  reloadFigure();refreshCounts();refreshCurrentView();
}

function priceHistoryHtml(prices){
  const points=[...prices].sort((a,b)=>a.observed_at.localeCompare(b.observed_at)||a.id-b.id);
  if(points.length<2)return '';
  const width=300,height=80,pad=8,amounts=points.map(point=>point.amount);
  const min=Math.min(...amounts),max=Math.max(...amounts),range=max-min;
  const t0=new Date(points[0].observed_at).getTime(),span=(new Date(points.at(-1).observed_at).getTime()-t0)||1;
  const coords=points.map(point=>[(new Date(point.observed_at).getTime()-t0)/span*width,pad+(1-(range?(point.amount-min)/range:.5))*(height-2*pad)]);
  const line=coords.map(([x,y],i)=>`${i?'L':'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const delta=points.at(-1).amount-points[0].amount;
  return `<div class="price-history"><div class="price-history-head"><span>${date(points[0].observed_at)} – ${date(points.at(-1).observed_at)}</span><b class="price-history-delta ${delta>0?'up':delta<0?'down':'flat'}">${delta>0?'+':''}${money(delta)}</b></div>
    <svg class="price-history-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Verlauf des Marktwerts"><path class="price-history-area" d="${line} L${width},${height} L0,${height} Z"/><path class="price-history-line" d="${line}"/></svg>
    <div class="price-history-range"><span>Tief ${money(min)}</span><span>Hoch ${money(max)}</span></div></div>`;
}

// ---- Copies -------------------------------------------------------------------------------------

async function openEntryDialog(figure,entry=null){
  const suggestions=await loadSuggestions().catch(()=>({}));
  const conditions=Object.entries(state.boot.conditions);
  const value=key=>escapeHtml(entry?.[key]??'');
  const modal=openDialog({id:'entry-dialog',eyebrow:'SAMMLUNG',title:entry?'Exemplar bearbeiten':'Exemplar hinzufügen',intro:escapeHtml(figure.name),stack:true,body:`
    <div class="dl-grid">
      <label class="dl-field"><span>Anzahl</span><input class="dl-control" data-field="quantity" type="number" min="1" max="999" value="${entry?.quantity??1}"></label>
      <label class="dl-field"><span>Zustand</span><select class="dl-control" data-field="condition">${conditions.map(([key,label])=>`<option value="${key}" ${(entry?.condition||'boxed')===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select></label>
      <label class="dl-field"><span>Kaufpreis je Stück (€)</span><input class="dl-control" data-field="purchase_price" inputmode="decimal" placeholder="z. B. 189,90" value="${amountValue(entry?.purchase_price)}"></label>
      <label class="dl-field"><span>Kaufdatum</span><input class="dl-control" data-field="purchased_at" placeholder="TT.MM.JJJJ oder JJJJ-MM" value="${escapeHtml(entry?.purchased_at||'')}"></label>
      <label class="dl-field"><span>Shop / Verkäufer</span><input class="dl-control" data-field="shop" list="shop-suggestions" value="${value('shop')}"></label>
      <label class="dl-field"><span>Aufbewahrung</span><input class="dl-control" data-field="location" list="location-suggestions" placeholder="z. B. Vitrine 2" value="${value('location')}"></label>
      <label class="dl-field dl-field-wide"><span>Notizen</span><textarea class="dl-control" data-field="notes" rows="2">${value('notes')}</textarea></label>
    </div>
    ${datalist('shop-suggestions',suggestions.shop)}${datalist('location-suggestions',suggestions.location)}
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" id="entry-save">${entry?'Speichern':'Hinzufügen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('#entry-save',modal).onclick=async()=>{
    const values=fieldValues(modal);
    try{
      if(entry)await patch(`/api/collection/${entry.id}`,values);
      else await post('/api/collection',{figure_id:figure.id,...values});
      closeDialog();toast(entry?'Exemplar gespeichert':'Zur Sammlung hinzugefügt');state.suggestions=null;afterChange();
    }catch(error){toast(error.message)}
  };
}

// ---- Preorders ----------------------------------------------------------------------------------

async function openPreorderDialog(figure,preorder=null,prefill={}){
  const suggestions=await loadSuggestions().catch(()=>({}));
  const item={quantity:1,status:'ordered',expected_release:figure.release_date||'',...prefill,...(preorder||{})};
  const value=key=>escapeHtml(item[key]??'');
  const statuses=Object.entries(state.boot.statuses);
  const delays=preorder?.events?.filter(event=>event.kind==='release')||[];
  const modal=openDialog({id:'preorder-dialog',eyebrow:'VORBESTELLUNG',title:preorder?'Vorbestellung bearbeiten':'Vorbestellen',intro:escapeHtml(figure.name||figure.figure_name),stack:true,body:`
    <div class="dl-grid">
      <label class="dl-field"><span>Status</span><select class="dl-control" data-field="status">${statuses.map(([key,label])=>`<option value="${key}" ${item.status===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select></label>
      <label class="dl-field"><span>Erwartet</span><input class="dl-control" data-field="expected_release" placeholder="z. B. 2026-03" value="${value('expected_release')}"></label>
      <label class="dl-field"><span>Shop</span><input class="dl-control" data-field="shop" list="preorder-shop-suggestions" value="${value('shop')}"></label>
      <label class="dl-field"><span>Bestellnummer</span><input class="dl-control" data-field="order_number" value="${value('order_number')}"></label>
      <label class="dl-field"><span>Bestellt am</span><input class="dl-control" data-field="ordered_at" placeholder="heute" value="${value('ordered_at')}"></label>
      <label class="dl-field"><span>Anzahl</span><input class="dl-control" data-field="quantity" type="number" min="1" max="99" value="${item.quantity}"></label>
      <label class="dl-field"><span>Preis gesamt (€)</span><input class="dl-control" data-field="price" inputmode="decimal" value="${amountValue(item.price)}"></label>
      <label class="dl-field"><span>Versand & Gebühren (€)</span><input class="dl-control" data-field="shipping" inputmode="decimal" value="${amountValue(item.shipping)}"></label>
      <label class="dl-field"><span>Schon bezahlt (€)</span><input class="dl-control" data-field="paid" inputmode="decimal" placeholder="z. B. Anzahlung" value="${amountValue(item.paid||'')}"></label>
      <label class="dl-field"><span>Sendungsnummer</span><input class="dl-control" data-field="tracking" value="${value('tracking')}"></label>
      <label class="dl-field dl-field-wide"><span>Notizen</span><textarea class="dl-control" data-field="notes" rows="2">${value('notes')}</textarea></label>
      ${!preorder&&figure.wished?'<label class="checkbox-row dl-field-wide"><span><b>Von den Wunschlisten nehmen</b><small>Die Figur ist bestellt, sie muss nicht mehr gesucht werden.</small></span><input type="checkbox" data-field="remove_from_wishlists" checked><i aria-hidden="true"></i></label>':''}
    </div>
    ${datalist('preorder-shop-suggestions',suggestions.shop)}
    ${delays.length?`<div class="fig-delays"><b>Verschiebungen</b>${delays.map(event=>`<span>${escapeHtml(partialDate(event.old_value)||'–')} → ${escapeHtml(partialDate(event.new_value)||'–')} <small>${date(event.created_at)}</small></span>`).join('')}</div>`:''}
    <p class="muted">„Angekommen“ bucht die Exemplare als neu und versiegelt in die Sammlung, mit dem Preis je Stück inklusive Versand.</p>
    <div class="dl-modal-actions">${preorder?'<button type="button" class="secondary-button danger" id="preorder-delete">Löschen</button>':'<button type="button" class="secondary-button" data-dialog-close>Abbrechen</button>'}<span class="spacer"></span><button type="button" class="primary-button" id="preorder-save">${preorder?'Speichern':'Vorbestellung anlegen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('#preorder-save',modal).onclick=async()=>{
    const values=fieldValues(modal);
    try{
      if(preorder)await patch(`/api/preorders/${preorder.id}`,values);
      else await post('/api/preorders',{figure_id:figure.id??figure.figure_id,...values});
      closeDialog();toast(values.status==='delivered'?'Angekommen – in die Sammlung gebucht':preorder?'Vorbestellung gespeichert':'Vorbestellung angelegt');state.suggestions=null;afterChange();
    }catch(error){toast(error.message)}
  };
  $('#preorder-delete',modal)?.addEventListener('click',async()=>{
    if(!confirm('Diese Vorbestellung löschen? Bereits eingebuchte Exemplare bleiben in der Sammlung.'))return;
    try{await del(`/api/preorders/${preorder.id}`);closeDialog();toast('Vorbestellung gelöscht');afterChange()}catch(error){toast(error.message)}
  });
}

// ---- Wishlists ----------------------------------------------------------------------------------

async function openWishDialog(figureId){
  let figure;
  try{figure=state.modalFigure?.id===figureId?state.modalFigure:await api(`/api/figures/${figureId}`)}catch(error){toast(error.message);return}
  const memberships=new Map(figure.lists.map(item=>[item.list_id,item]));
  const modal=openDialog({id:'wish-dialog',eyebrow:'WUNSCHLISTEN',title:'Auf welche Listen?',intro:escapeHtml(figure.name),stack:true,body:`
    <div class="fig-rows">${state.boot.watchlists.map(list=>{const entry=memberships.get(list.id);return `<label class="fig-row fig-list-row"><span class="fig-list-toggle"><input type="checkbox" data-wish-list="${list.id}" ${entry||(!figure.lists.length&&list.is_default)?'checked':''}><b>${escapeHtml(list.name)}</b></span></label>`}).join('')}</div>
    <div class="dl-grid">
      <label class="dl-field"><span>Zielpreis (€)</span><input class="dl-control" data-field="target_price" inputmode="decimal" placeholder="optional" value="${amountValue(figure.lists[0]?.target_price)}"></label>
      <label class="dl-field"><span>Notiz</span><input class="dl-control" data-field="note" placeholder="z. B. nur mit Bonusteil" value="${escapeHtml(figure.lists[0]?.note??'')}"></label>
      <label class="dl-field dl-field-wide"><span>Neue Liste</span><input class="dl-control" id="wish-new-list" placeholder="Name einer neuen Liste (optional)"></label>
    </div>
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" id="wish-save">Speichern</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  $('#wish-save',modal).onclick=async()=>{
    const values=fieldValues(modal);
    try{
      const newName=$('#wish-new-list',modal).value.trim();
      const chosen=$$('[data-wish-list]',modal).filter(box=>box.checked).map(box=>Number(box.dataset.wishList));
      if(newName)chosen.push((await post('/api/watchlists',{name:newName})).id);
      for(const list of state.boot.watchlists){
        if(memberships.has(list.id)&&!chosen.includes(list.id))await del(`/api/watchlists/${list.id}/figures/${figure.id}`);
      }
      for(const listId of chosen)await post(`/api/watchlists/${listId}/figures`,{figure_id:figure.id,...values});
      closeDialog();toast('Wunschlisten gespeichert');afterChange();
    }catch(error){toast(error.message)}
  };
}

// ---- Pictures -----------------------------------------------------------------------------------

// What the server takes (images.py FORMATS); the file pickers offer these.
const PICTURE_TYPES='image/jpeg,image/png,image/webp,image/gif,image/avif';

function openImageDialog(figure){
  const modal=openDialog({id:'image-dialog',eyebrow:'BILD',title:'Bild der Figur',intro:escapeHtml(figure.name),stack:true,body:`
    <div class="dl-grid">
      <label class="dl-field dl-field-wide"><span>Datei hochladen</span><input class="dl-control" type="file" id="image-file" accept="${PICTURE_TYPES}"></label>
      <label class="dl-field dl-field-wide"><span>… oder Link zu einem Bild</span><input class="dl-control" id="image-url" placeholder="https://…/bild.jpg" value="${escapeHtml(figure.image_url||'')}"></label>
    </div>
    <div class="dl-modal-actions">${figure.has_image?'<button type="button" class="secondary-button danger" id="image-remove">Bild entfernen</button>':''}<span class="spacer"></span><button type="button" class="primary-button" id="image-save">Übernehmen</button></div>`});
  $('#image-save',modal).onclick=async()=>{
    const file=$('#image-file',modal).files[0],url=$('#image-url',modal).value.trim();
    try{
      if(file)await uploadFigureImage(figure.id,file);
      else if(url)await post(`/api/figures/${figure.id}/image`,{url});
      else{toast('Bitte eine Datei oder einen Link wählen.');return}
      closeDialog();toast('Bild gespeichert');afterChange();
    }catch(error){toast(error.message)}
  };
  $('#image-remove',modal)?.addEventListener('click',async()=>{
    try{await del(`/api/figures/${figure.id}/image`);closeDialog();afterChange()}catch(error){toast(error.message)}
  });
}

async function uploadFigureImage(figureId,file){
  const form=new FormData();form.append('file',file);
  const response=await fetch(appUrl(`/api/figures/${figureId}/image`),{method:'POST',body:form});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data.error||'Upload fehlgeschlagen');
  return data;
}

// ---- A figure: create, correct, fill in from a link ---------------------------------------------

// The form's fields in sections: [key, label, wide, suggestion list, placeholder]. The line comes
// first in its section, so its preset fills the fields that follow it.
const FIGURE_SECTIONS=[
  ['Figur',[['name','Name *','wide'],['original_name','Originalname (japanisch)','wide'],['characters','Charaktere','','character'],['series','Franchise','','series']]],
  ['Linie & Hersteller',[['line','Linie','','line'],['brand','Marke','','brand'],['manufacturer','Hersteller','','manufacturer'],['category','Kategorie','','category'],['scale','Maßstab','','scale'],['material','Material','','material']]],
  ['Details',[['edition','Edition','','edition'],['release_date','Erscheinung','',null,'z. B. 2026-03'],['height_mm','Höhe (mm)','',null,'z. B. 240'],['jan','JAN / EAN'],['sculptor','Sculptor','','sculptor']]],
];

async function openFigureForm(prefill={},{figureId=null,importResult=null}={}){
  const [suggestions]=await Promise.all([loadSuggestions().catch(()=>({})),loadLinePresets().catch(()=>null)]);
  const editing=Boolean(figureId);
  const value=key=>escapeHtml(prefill[key]??'');
  const currencies=suggestions.currencies||['JPY','EUR','USD'];
  const input=([key,label,wide,list,placeholder])=>`<label class="dl-field${wide?' dl-field-wide':''}"><span>${label}</span><input class="dl-control" data-field="${key}" ${list?`list="suggest-${list}"`:''} ${placeholder?`placeholder="${placeholder}"`:''} value="${value(key)}" autocomplete="off"></label>`;
  const section=(title,body,extra='')=>`<section class="fig-form-section"><h3>${title}</h3>${extra}<div class="dl-grid fig-form-grid">${body}</div></section>`;
  const modal=openDialog({id:'figure-form',eyebrow:'KATALOG',title:editing?'Figur bearbeiten':'Figur anlegen',wide:true,stack:editing,
    intro:editing?'Der Katalog ist für alle Konten gemeinsam – Korrekturen sehen alle.':'Füge einen Link ein, um die Daten zu übernehmen, oder trage sie von Hand ein.',body:`
    ${editing?'':`<div class="fig-import">
      <input class="dl-control" id="import-url" placeholder="Link zur Produktseite: Shop, Hersteller, Datenbank …" autocomplete="off">
      <button type="button" class="secondary-button" id="import-fetch">Daten holen</button>
      <small class="muted">Viele Seiten (z. B. MyFigureCollection, AmiAmi) blocken automatische Abrufe. Dann hilft das Lesezeichen <a href="${bookmarkletHref()}" class="fig-bookmarklet" title="In die Lesezeichenleiste ziehen">„Zu Ophir Figures“</a>: in die Lesezeichenleiste ziehen und auf der Produktseite anklicken.</small>
    </div>`}
    <div id="import-result">${importResult?importResultHtml(importResult):''}</div>
    ${FIGURE_SECTIONS.map(([title,fields])=>section(title,fields.map(input).join(''),title==='Linie & Hersteller'?'<p class="fig-preset-hint" id="preset-hint" aria-live="polite"></p>':'')).join('')}
    ${section('Preis & Bild',`
      <label class="dl-field"><span>Originalpreis</span><span class="fig-price-input"><input class="dl-control" data-field="msrp" inputmode="decimal" value="${amountValue(prefill.msrp)}"><select class="dl-control" data-field="msrp_currency" aria-label="Währung">${currencies.map(code=>`<option ${(prefill.msrp_currency||'JPY')===code?'selected':''}>${code}</option>`).join('')}</select></span></label>
      ${editing?'':`<label class="dl-field"><span>Marktwert (€)</span><input class="dl-control" data-field="market_value" inputmode="decimal" placeholder="optional" value="${amountValue(prefill.market_value)}"></label>`}
      <label class="dl-field dl-field-wide"><span>Bild-Link</span><input class="dl-control" data-field="image_url" placeholder="https://…/bild.jpg" value="${value('image_url')}"></label>
      ${editing?'':`<label class="dl-field dl-field-wide"><span>… oder Bild hochladen</span><input class="dl-control" type="file" id="figure-image-file" accept="${PICTURE_TYPES}"></label>`}`)}
    ${section('Quelle & Beschreibung',`
      ${input(['source_url','Link zur Quelle','wide',null,'https://…'])}
      <label class="dl-field dl-field-wide"><span>Beschreibung</span><textarea class="dl-control" data-field="description" rows="3">${value('description')}</textarea></label>
      ${editing?'':`<label class="dl-field dl-field-wide"><span>Danach</span><select class="dl-control" id="figure-after">
        <option value="open">Nur in den Katalog</option><option value="copy">Zur Sammlung hinzufügen</option><option value="preorder">Vorbestellen</option><option value="wish">Auf die Wunschliste</option></select></label>`}`)}
    ${['character','series','manufacturer','brand','category','line','scale','edition','sculptor','material'].map(key=>datalist(`suggest-${key}`,suggestions[key]||[])).join('')}
    <div class="dl-modal-actions"><button type="button" class="secondary-button" data-dialog-close>Abbrechen</button><span class="spacer"></span><button type="button" class="primary-button" id="figure-save">${editing?'Speichern':'Figur anlegen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  let offer=importResult?.offer||null,fromImport=Boolean(importResult);
  const fill=fields=>{
    for(const [key,fieldValue] of Object.entries(fields)){const input=$(`[data-field="${key}"]`,modal);if(input&&fieldValue!=null)input.value=fieldValue}
  };
  const presets=wireLinePreset(modal,{applyNow:!editing&&Boolean(prefill.line)});
  if(importResult?.preset)presets.filledBy(importResult.preset);
  const runImport=async()=>{
    const url=$('#import-url',modal).value.trim();
    if(!url){toast('Bitte einen Link einfügen.');return}
    const button=$('#import-fetch',modal);button.disabled=true;button.textContent='Wird gelesen …';
    try{
      const result=await post('/api/figures/link-import',{url});
      fill(result.fields);offer=result.offer;fromImport=true;
      if(result.preset)presets.filledBy(result.preset);
      presets.apply();
      $('#import-result',modal).innerHTML=importResultHtml(result);wireImportResult(modal);
    }catch(error){
      $('#import-result',modal).innerHTML=`<div class="fig-import-note warning"><b>Nicht übernommen</b><span>${escapeHtml(error.message)}</span></div>`;
      if(!$('[data-field="source_url"]',modal).value)$('[data-field="source_url"]',modal).value=url;
    }finally{button.disabled=false;button.textContent='Daten holen'}
  };
  $('#import-fetch',modal)?.addEventListener('click',runImport);
  $('#import-url',modal)?.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();runImport()}});
  $('#import-url',modal)?.addEventListener('paste',()=>setTimeout(runImport,50));
  wireImportResult(modal);
  const save=async force=>{
    const values=fieldValues(modal);
    if(!values.name.trim()){toast('Der Name fehlt.');return}
    const button=$('#figure-save',modal);button.disabled=true;
    try{
      const result=editing?await patch(`/api/figures/${figureId}`,{...values,force}):await post('/api/figures',{...values,force,from_import:fromImport});
      if(result.image_error)toast(`Bild nicht geladen: ${result.image_error}`);
      const file=$('#figure-image-file',modal)?.files[0];
      if(file)await uploadFigureImage(result.id,file).catch(error=>toast(error.message));
      const after=$('#figure-after',modal)?.value||'open';
      closeDialog();state.suggestions=null;refreshCounts();
      if(editing){toast('Figur gespeichert');afterChange();return}
      toast('Figur angelegt');refreshCurrentView();
      await openFigure(result.id,after==='preorder'?'preorders':'copies');
      if(after==='copy')openEntryDialog(result);
      if(after==='preorder')openPreorderDialog(result,null,offer&&offer.currency==='EUR'?{price:offer.price}:{});
      if(after==='wish'){await post(`/api/watchlists/${defaultListId()}/figures`,{figure_id:result.id});afterChange();toast('Auf die Wunschliste gesetzt')}
    }catch(error){
      button.disabled=false;
      if(error.status===409&&error.data?.duplicate_id){
        $('#import-result',modal).innerHTML=`<div class="fig-import-note warning"><b>Schon im Katalog?</b><span>${escapeHtml(error.message)}</span><span class="fig-import-actions"><button type="button" class="secondary-button" data-open-duplicate="${error.data.duplicate_id}">Vorhandene öffnen</button><button type="button" class="link-button" id="figure-force">Trotzdem ${editing?'speichern':'anlegen'}</button></span></div>`;
        wireImportResult(modal);
        $('#figure-force',modal).onclick=()=>save(true);
        $('#import-result',modal).scrollIntoView({behavior:'smooth',block:'nearest'});
      }else toast(error.message);
    }
  };
  $('#figure-save',modal).onclick=()=>save(false);
}

function importResultHtml(result){
  const parts=[];
  if(result.duplicate)parts.push(`<div class="fig-import-note warning"><b>Schon im Katalog</b><span>„${escapeHtml(result.duplicate.name)}“ (${escapeHtml(result.duplicate.reason)}).</span><span class="fig-import-actions"><button type="button" class="secondary-button" data-open-duplicate="${result.duplicate.id}">Vorhandene öffnen</button></span></div>`);
  const count=Object.keys(result.fields||{}).length;
  const fromPreset=result.preset?.applied?.length?`<span>Aus der Vorlage „${escapeHtml(result.preset.line)}“: ${result.preset.applied.map(key=>PRESET_LABELS[key]||key).join(', ')}</span>`:'';
  parts.push(`<div class="fig-import-note ${count>3?'ok':'warning'}"><b>${count} Felder übernommen</b>${fromPreset}${(result.warnings||[]).map(text=>`<span>${escapeHtml(text)}</span>`).join('')}${result.offer?`<span>Preis auf der Seite: ${escapeHtml(currencyMoney(result.offer.price,result.offer.currency||'EUR'))}</span>`:''}</div>`);
  const unmapped=Object.entries(result.unmapped||{});
  if(unmapped.length)parts.push(`<details class="fig-import-unmapped"><summary>Weitere Angaben der Seite (${unmapped.length})</summary><dl class="fig-facts">${unmapped.map(([key,value])=>factRow(escapeHtml(key),escapeHtml(value))).join('')}</dl></details>`);
  return parts.join('');
}

function wireImportResult(modal){
  $$('[data-open-duplicate]',modal).forEach(button=>button.onclick=()=>{closeDialog();openFigure(Number(button.dataset.openDuplicate))});
}

// ---- Line presets -------------------------------------------------------------------------------

// What a preset fixes (line_presets.py PRESET_FIELDS), in the form's order.
const PRESET_FIELDS=[['brand','Marke'],['manufacturer','Hersteller'],['category','Kategorie'],['scale','Maßstab'],['material','Material']];
const PRESET_LABELS=Object.fromEntries(PRESET_FIELDS);
// As line_presets.line_key: spacing and case aside.
const lineKey=text=>String(text??'').trim().split(/\s+/).join(' ').toLowerCase();
const presetSummary=preset=>PRESET_FIELDS.map(([key])=>preset[key]).filter(Boolean).join(' · ');

async function loadLinePresets(force=false){
  if(!state.linePresets||force)state.linePresets=await api('/api/line-presets');
  return state.linePresets;
}
function presetForLine(line){
  const key=lineKey(line);
  return key&&state.linePresets?state.linePresets.presets.find(preset=>lineKey(preset.line)===key)||null:null;
}
// A line group's tile says when its line has a preset.
const presetBadge=(by,group)=>by==='line'&&presetForLine(group.name)?'<span class="fig-preset-badge">Vorlage</span>':'';

// In a figure form: choosing a line with a preset fills the preset's fields that are empty or still
// hold what a preset put there; a value someone typed stays, and the hint offers the preset's.
// fill=false (an existing figure, just opened) only says what the preset would change.
function wireLinePreset(root,{applyNow=false}={}){
  const line=$('[data-field="line"]',root),hint=$('#preset-hint',root);
  const field=key=>$(`[data-field="${key}"]`,root);
  const filled={};
  const apply=(fill=true)=>{
    const preset=presetForLine(line.value),name=line.value.trim();
    if(!preset){
      hint.innerHTML=name?`<span>Keine Vorlage für „${escapeHtml(name)}“.</span> <button type="button" class="link-button" data-preset-new>Als Vorlage speichern</button>`:'';
      wire(null);return;
    }
    const taken=[],differ=[];
    for(const [key,label] of PRESET_FIELDS){
      const input=field(key),current=input.value.trim();
      if(!preset[key]||current===preset[key])continue;
      if(fill&&(!current||filled[key]===current)){input.value=preset[key];filled[key]=preset[key];taken.push(label)}
      else differ.push(label);
    }
    hint.innerHTML=`<span><b>Vorlage „${escapeHtml(preset.line)}“</b>${taken.length?` – übernommen: ${taken.join(', ')}`:differ.length?'':' – alles wie in der Vorlage'}</span>
      ${differ.length?`<span>${fill?'Anders als in der Vorlage':'Laut Vorlage anders'}: ${differ.join(', ')} <button type="button" class="link-button" data-preset-take>Vorlage übernehmen</button></span>`:''}
      <button type="button" class="link-button" data-preset-edit>Vorlage bearbeiten</button>`;
    wire(preset);
  };
  const current=()=>Object.fromEntries(['line',...PRESET_FIELDS.map(([key])=>key)].map(key=>[key,field(key).value.trim()]));
  const wire=preset=>{
    $('[data-preset-new]',hint)?.addEventListener('click',()=>openPresetForm(null,current(),{onSaved:()=>apply()}));
    $('[data-preset-edit]',hint)?.addEventListener('click',()=>openPresetForm(preset,{},{onSaved:()=>apply()}));
    $('[data-preset-take]',hint)?.addEventListener('click',()=>{
      for(const [key] of PRESET_FIELDS)if(preset[key]){field(key).value=preset[key];filled[key]=preset[key]}
      apply();
    });
  };
  let timer;
  line.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,250)});
  line.addEventListener('change',()=>{clearTimeout(timer);apply()});
  // A filled-in value someone types over is theirs from then on.
  for(const [key] of PRESET_FIELDS)field(key).addEventListener('input',()=>{if(filled[key]!==field(key).value.trim())delete filled[key]});
  apply(applyNow);
  return {apply,filledBy:preset=>{for(const key of preset.applied||[])filled[key]=field(key)?.value.trim()}};
}

// One preset: create (preset null, prefill from a form or a catalogue line) or correct it.
async function openPresetForm(preset=null,prefill={},{onSaved=null}={}){
  const [suggestions]=await Promise.all([loadSuggestions().catch(()=>({})),loadLinePresets().catch(()=>null)]);
  const item={...prefill,...(preset||{})};
  const modal=openDialog({id:'preset-form',eyebrow:'LINIEN-VORLAGE',title:preset?`Vorlage „${escapeHtml(preset.line)}“`:'Neue Linien-Vorlage',stack:true,
    intro:'Was du hier einträgst, füllt sich bei jeder Figur dieser Linie von selbst aus – im Formular und beim Import aus einem Link. Bei der einzelnen Figur bleibt es änderbar.',body:`
    <div class="dl-grid">
      <label class="dl-field dl-field-wide"><span>Linie *</span><input class="dl-control" data-field="line" list="preset-suggest-line" placeholder="z. B. Nendoroid, figma, POP UP PARADE" value="${escapeHtml(item.line||'')}" autocomplete="off"></label>
      ${PRESET_FIELDS.map(([key,label])=>`<label class="dl-field"><span>${label}</span><input class="dl-control" data-field="${key}" list="preset-suggest-${key}" value="${escapeHtml(item[key]||'')}" autocomplete="off"></label>`).join('')}
    </div>
    <div id="preset-note">${preset?.figures?`<div class="fig-import-note ${preset.incomplete?'warning':'ok'}"><b>${plural(preset.figures,'Figur','Figuren')} dieser Linie im Katalog</b><span>${preset.incomplete?`Bei ${plural(preset.incomplete,'Figur','Figuren')} sind Felder leer, die die Vorlage füllen kann.`:'Alle haben die Angaben der Vorlage schon (oder eigene).'}</span>${preset.incomplete?'<span class="fig-import-actions"><button type="button" class="secondary-button" id="preset-apply">Speichern und leere Felder ergänzen</button></span>':''}</div>`:''}</div>
    ${['line',...PRESET_FIELDS.map(([key])=>key)].map(key=>datalist(`preset-suggest-${key}`,suggestions[key]||[])).join('')}
    <div class="dl-modal-actions">${preset?.can_delete?'<button type="button" class="secondary-button danger" id="preset-delete">Löschen</button>':'<button type="button" class="secondary-button" data-dialog-close>Abbrechen</button>'}<span class="spacer"></span><button type="button" class="primary-button" id="preset-save">${preset?'Speichern':'Vorlage anlegen'}</button></div>`});
  $$('[data-dialog-close]',modal).forEach(button=>button.onclick=closeDialog);
  const save=async()=>{
    try{
      const saved=preset?await patch(`/api/line-presets/${preset.id}`,fieldValues(modal)):await post('/api/line-presets',fieldValues(modal));
      await loadLinePresets(true);
      return saved;
    }catch(error){
      if(error.status===409&&error.data?.preset_id){
        $('#preset-note',modal).innerHTML=`<div class="fig-import-note warning"><b>Schon vorhanden</b><span>${escapeHtml(error.message)}</span><span class="fig-import-actions"><button type="button" class="secondary-button" id="preset-open-existing">Vorhandene bearbeiten</button></span></div>`;
        $('#preset-open-existing',modal).onclick=()=>{closeDialog();openPresetForm(state.linePresets?.presets.find(other=>other.id===error.data.preset_id)||null,{},{onSaved})};
      }else toast(error.message);
      return null;
    }
  };
  $('#preset-save',modal).onclick=async()=>{
    const saved=await save();if(!saved)return;
    closeDialog();toast(preset?'Vorlage gespeichert':'Vorlage angelegt');onSaved?.(saved);
  };
  $('#preset-apply',modal)?.addEventListener('click',async()=>{
    const saved=await save();if(!saved)return;
    try{
      const result=await post(`/api/line-presets/${saved.id}/apply`,{});
      await loadLinePresets(true);
      closeDialog();toast(result.updated?`${plural(result.updated,'Figur','Figuren')} ergänzt`:'Nichts zu ergänzen');
      state.suggestions=null;onSaved?.(saved);refreshCurrentView();
    }catch(error){toast(error.message)}
  });
  $('#preset-delete',modal)?.addEventListener('click',async()=>{
    if(!confirm(`Vorlage „${preset.line}“ löschen? Die Figuren der Linie bleiben, wie sie sind.`))return;
    try{await del(`/api/line-presets/${preset.id}`);await loadLinePresets(true);closeDialog();toast('Vorlage gelöscht');onSaved?.(null)}catch(error){toast(error.message)}
  });
}

// Where presets are managed: every preset, and the catalogue's lines that have none yet, each
// with what its figures mostly say.
async function openLinePresets(){
  try{await loadLinePresets(true)}catch(error){toast(error.message);return}
  const modal=openDialog({id:'line-presets',eyebrow:'KATALOG',title:'Linien-Vorlagen',wide:true,
    intro:'Eine Vorlage hält fest, was eine Linie vorgibt: Marke, Hersteller, Kategorie, Maßstab, Material. Wählst du die Linie bei einer Figur – oder bringt der Link-Import sie mit –, füllen sich diese Felder von selbst.',
    body:'<div id="line-presets-body"></div>'});
  const body=$('#line-presets-body',modal);
  const refresh=async()=>{await loadLinePresets(true);if(document.body.contains(body))paint()};
  const paint=()=>{
    const {presets,lines}=state.linePresets;
    body.innerHTML=`<div class="fig-section-head"><h3>Vorlagen <small>${presets.length}</small></h3><button type="button" class="primary-button" data-preset-create>＋ Vorlage</button></div>
      ${presets.length?`<div class="fig-rows">${presets.map(preset=>`<div class="fig-row fig-preset-row">
          <span class="fig-preset-main"><b>${escapeHtml(preset.line)}</b><small>${escapeHtml(presetSummary(preset))}</small>
            <small>${preset.figures?plural(preset.figures,'Figur','Figuren'):'Noch keine Figur'}${preset.incomplete?` · <span class="fig-incomplete">${preset.incomplete} mit leeren Feldern</span>`:''}</small></span>
          <span class="fig-row-actions">${preset.incomplete?`<button type="button" class="secondary-button" data-preset-apply="${preset.id}" title="Leere Felder der Figuren dieser Linie aus der Vorlage füllen">Ergänzen</button>`:''}<button type="button" class="icon-button" data-preset-edit="${preset.id}" title="Bearbeiten" aria-label="Vorlage ${escapeHtml(preset.line)} bearbeiten">✎</button>${preset.can_delete?`<button type="button" class="icon-button" data-preset-delete="${preset.id}" title="Löschen" aria-label="Vorlage ${escapeHtml(preset.line)} löschen">✕</button>`:''}</span>
        </div>`).join('')}</div>`
        :'<div class="fig-empty-soft">Noch keine Vorlage. Leg eine an – oder starte mit einer Linie aus dem Katalog.</div>'}
      ${lines.length?`<div class="fig-section-head"><h3>Linien im Katalog ohne Vorlage <small>${lines.length}</small></h3></div>
        <div class="fig-rows">${lines.map((line,index)=>`<div class="fig-row fig-preset-row">
          <span class="fig-preset-main"><b>${escapeHtml(line.line)}</b><small>${plural(line.figures,'Figur','Figuren')}${presetSummary(line.common)?` · meist ${escapeHtml(presetSummary(line.common))}`:''}</small></span>
          <span class="fig-row-actions"><button type="button" class="secondary-button" data-line-create="${index}">Vorlage anlegen</button></span>
        </div>`).join('')}</div>`:''}`;
    $('[data-preset-create]',body).onclick=()=>openPresetForm(null,{},{onSaved:refresh});
    $$('[data-line-create]',body).forEach(button=>button.onclick=()=>{const line=lines[Number(button.dataset.lineCreate)];openPresetForm(null,{line:line.line,...line.common},{onSaved:refresh})});
    $$('[data-preset-edit]',body).forEach(button=>button.onclick=()=>openPresetForm(presets.find(preset=>preset.id===Number(button.dataset.presetEdit)),{},{onSaved:refresh}));
    $$('[data-preset-apply]',body).forEach(button=>button.onclick=async()=>{
      try{const result=await post(`/api/line-presets/${button.dataset.presetApply}/apply`,{});toast(`${plural(result.updated,'Figur','Figuren')} ergänzt`);state.suggestions=null;refreshCurrentView();refresh()}
      catch(error){toast(error.message)}
    });
    $$('[data-preset-delete]',body).forEach(button=>button.onclick=async()=>{
      const preset=presets.find(item=>item.id===Number(button.dataset.presetDelete));
      if(!confirm(`Vorlage „${preset.line}“ löschen? Die Figuren der Linie bleiben, wie sie sind.`))return;
      try{await del(`/api/line-presets/${preset.id}`);toast('Vorlage gelöscht');refresh()}catch(error){toast(error.message)}
    });
  };
  paint();
}

// ---- The bookmarklet ----------------------------------------------------------------------------

// Runs on a product page in the user's own browser: gathers meta tags, JSON-LD and label/value
// pairs (as ophir_figures/link_import.py reads them) and opens the app with them in the address's
// fragment, which never reaches a server log. The page is only read, never changed or sent elsewhere.
function bookmarkletHref(){
  const code=`(()=>{const d=document,m={},j=[],f={};d.querySelectorAll('meta[property],meta[name],meta[itemprop]').forEach(e=>{const k=e.getAttribute('property')||e.getAttribute('name')||e.getAttribute('itemprop');if(k&&e.content&&!(k in m))m[k]=e.content.slice(0,2000)});d.querySelectorAll('script[type="application/ld+json"]').forEach(s=>{try{j.push(JSON.parse(s.textContent))}catch(e){}});const a=(l,v)=>{l=(l||'').replace(/\\s+/g,' ').trim().replace(/[:：]$/,'');v=(v||'').replace(/\\s+/g,' ').trim();if(l&&v&&l.length<60&&!(l in f))f[l]=v.slice(0,500)};d.querySelectorAll('.data-field').forEach(e=>a(e.querySelector('.data-label')?.innerText,e.querySelector('.data-value')?.innerText));d.querySelectorAll('dt').forEach(e=>{const n=e.nextElementSibling;if(n&&n.tagName=='DD')a(e.innerText,n.innerText)});d.querySelectorAll('tr').forEach(r=>{const c=r.querySelectorAll(':scope>th,:scope>td');if(c.length==2)a(c[0].innerText,c[1].innerText)});const b={url:location.href,canonical:d.querySelector('link[rel=canonical]')?.href||'',title:d.title,heading:d.querySelector('h1')?.innerText||'',meta:m,jsonld:j,fields:f};let s=JSON.stringify(b);if(s.length>400000){b.jsonld=[];s=JSON.stringify(b)}const u='${location.origin}${APP_ROOT}/#import='+encodeURIComponent(s);window.open(u,'_blank')||(location.href=u)})()`;
  return `javascript:${encodeURIComponent(code)}`;
}

// The app opened by the bookmarklet: read what it brought and open the form with it.
async function handleImportFragment(){
  if(!location.hash.startsWith('#import='))return;
  let snapshot;
  try{snapshot=JSON.parse(decodeURIComponent(location.hash.slice('#import='.length)))}catch{toast('Die Seitendaten vom Lesezeichen waren unvollständig.');return}
  finally{history.replaceState(null,'',location.pathname)}
  try{
    const result=await post('/api/figures/link-import',{snapshot});
    openFigureForm(result.fields,{importResult:result});
  }catch(error){toast(error.message)}
}
