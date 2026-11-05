// The four lists of figures: catalogue, collection, wishlists, preorders.

const CATALOG_MODES=[['all','Alle'],['missing','Nicht in der Sammlung'],['owned','In der Sammlung'],['wished','Gewünscht'],['preordered','Vorbestellt']];

function pageHead({eyebrow,title,text,actions=''}){
  return `<div class="page-head compact-page-head fig-page-head"><div><span class="eyebrow">${eyebrow}</span><h1>${title}</h1>${text?`<p>${text}</p>`:''}</div>${actions?`<div class="fig-head-actions">${actions}</div>`:''}</div>`;
}
const loader=text=>`<div class="page-loader"><span></span><p>${text}</p></div>`;

// ---- Catalogue ----------------------------------------------------------------------------------

async function renderCatalog(){
  const stale=renderGuard(),filters=state.catalogFilters;
  if(!$('#catalog-grid'))content.innerHTML=loader('Katalog wird geladen …');
  let data;
  try{data=await api(`/api/figures?${filterQuery(filters)}`)}catch(error){if(!stale())content.innerHTML=`<div class="empty-state"><b>Katalog nicht erreichbar</b><span>${escapeHtml(error.message)}</span></div>`;return}
  if(stale())return;
  content.innerHTML=`${pageHead({eyebrow:'GEMEINSAMER KATALOG',title:'Katalog',text:`${plural(data.total,'Figur','Figuren')} – von allen Konten gepflegt. Fehlt eine, leg sie an.`,
      actions:'<button type="button" class="primary-button" id="catalog-create">＋ Figur anlegen</button>'})}
    ${filterBar({key:'catalog',filters,facets:data.facets,modes:CATALOG_MODES,sorts:['release','name','manufacturer','added','value'],extraFacets:['line','scale']})}
    <p class="fig-count muted">${data.figures.length===data.total?plural(data.total,'Figur','Figuren'):`${data.figures.length} von ${data.total} Figuren`}</p>
    <div id="catalog-grid"></div>`;
  mountFilterPanel('catalog',['.fig-filter-row']);
  wireFilterBar(content,filters,renderCatalog,()=>{state.catalogFilters=Object.assign(filters,defaultCatalogFilters())});
  $('#catalog-create').onclick=()=>openFigureForm({name:filters.q||''});
  renderFigureGrid($('#catalog-grid'),data.figures,{empty:`<div class="empty-state"><b>${data.total?'Keine Figur passt zu den Filtern':'Der Katalog ist noch leer'}</b><span>${data.total?'Ändere die Filter oder ':''}Lege die erste Figur an – von Hand oder aus einem Link.</span><button type="button" class="primary-button" data-empty-create>＋ Figur anlegen</button></div>`});
  $('[data-empty-create]',content)?.addEventListener('click',()=>openFigureForm({name:filters.q||''}));
}

// ---- Collection ---------------------------------------------------------------------------------

async function renderCollection(){
  const stale=renderGuard(),filters=state.collectionFilters;
  if(!$('#collection-grid'))content.innerHTML=loader('Sammlung wird geladen …');
  let data;
  try{data=await api(`/api/collection?${filterQuery(filters)}`)}catch(error){if(!stale())content.innerHTML=`<div class="empty-state"><b>Sammlung nicht erreichbar</b><span>${escapeHtml(error.message)}</span></div>`;return}
  if(stale())return;
  const stats=data.stats;
  const conditionSelect=`<label class="fig-filter"><span>Zustand</span><select class="select-control" data-filter="condition"><option value="">Alle</option>${Object.entries(data.conditions).map(([key,label])=>`<option value="${key}" ${filters.condition===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select></label>`;
  content.innerHTML=`${pageHead({eyebrow:'MEINE SAMMLUNG',title:'Sammlung',text:stats.figures?'Was du besitzt, was es gekostet hat und was es wert ist.':'',
      actions:'<button type="button" class="secondary-button" id="collection-add">＋ Figur hinzufügen</button>'})}
    ${statPill([
      {label:'Figuren',value:stats.figures},{label:'Exemplare',value:stats.copies},
      {label:'Wert',value:money(stats.value)},{label:'Ausgegeben',value:money(stats.spent)},
    ],{className:'fig-summary',columns:4,mobileColumns:2})}
    ${filterBar({key:'collection',filters,facets:data.facets,sorts:['added','purchased','release','name','manufacturer','collection_value','spent'],extraFacets:['location'],extra:conditionSelect})}
    ${stats.unpriced?`<p class="muted fig-count">${plural(stats.unpriced,'Exemplar hat','Exemplare haben')} weder Kaufpreis noch Marktwert und zählen im Wert nicht mit.</p>`:''}
    <div id="collection-grid"></div>`;
  mountFilterPanel('collection',['.fig-filter-row']);
  wireFilterBar(content,filters,renderCollection,()=>{state.collectionFilters=Object.assign(filters,defaultCollectionFilters())});
  $('#collection-add').onclick=()=>{state.catalogFilters.mode='missing';routeTo('catalog')};
  renderFigureGrid($('#collection-grid'),data.figures,{
    tile:figure=>figureTile(figure,{value:figure.value||null,note:[figure.conditions.map(conditionLabel).join(', '),figure.locations.length?`📍 ${figure.locations.join(', ')}`:''].filter(Boolean).map(escapeHtml).join(' · ')}),
    empty:stats.figures?'<div class="empty-state"><b>Keine Figur passt zu den Filtern</b><span>Ändere oder setze die Filter zurück.</span></div>'
      :'<div class="empty-state"><b>Deine Sammlung ist noch leer</b><span>Such eine Figur im Katalog oder leg sie an und füge ein Exemplar hinzu.</span><button type="button" class="primary-button" data-route-catalog>Zum Katalog</button></div>'});
  $('[data-route-catalog]',content)?.addEventListener('click',()=>routeTo('catalog'));
}

// ---- Wishlists ----------------------------------------------------------------------------------

async function renderWatchlist(listId){
  const stale=renderGuard(),filters=state.watchFilters;
  const lists=state.boot.watchlists;
  if(listId)state.watchlistId=listId;
  if(!lists.some(list=>list.id===state.watchlistId))state.watchlistId=lists.find(list=>list.is_default)?.id||lists[0]?.id;
  if(!$('#watch-grid'))content.innerHTML=loader('Wunschliste wird geladen …');
  let data;
  try{data=await api(`/api/watchlists/${state.watchlistId}/figures?${filterQuery(filters)}`)}catch(error){if(!stale())content.innerHTML=`<div class="empty-state"><b>Liste nicht erreichbar</b><span>${escapeHtml(error.message)}</span></div>`;return}
  if(stale())return;
  const list=data.list,stats=data.stats;
  content.innerHTML=`${pageHead({eyebrow:'WUNSCHLISTEN',title:escapeHtml(list.name),text:'Figuren, die du noch suchst – mit Zielpreis wird markiert, was gerade günstig ist.',
      actions:`<button type="button" class="secondary-button" id="watch-new">＋ Neue Liste</button>${list.is_default?'':'<button type="button" class="secondary-button" id="watch-rename">Umbenennen</button><button type="button" class="icon-button" id="watch-delete" title="Liste löschen">✕</button>'}`})}
    <div class="fig-list-tabs">${lists.map(item=>`<button type="button" class="fig-list-tab${item.id===list.id?' active':''}" data-list="${item.id}">${escapeHtml(item.name)} <small>${item.count}</small></button>`).join('')}</div>
    ${statPill([
      {label:'Figuren',value:stats.count},{label:'Zielpreis erreicht',value:stats.target_reached,className:stats.target_reached?'complete':''},
      {label:'Schon in der Sammlung',value:stats.owned},{label:'Geschätzt',value:money(stats.estimate)},
    ],{className:'fig-summary',columns:4,mobileColumns:2})}
    ${filterBar({key:'watch',filters,facets:data.facets,modes:[['all','Alle'],['missing','Noch nicht in der Sammlung']],sorts:['wished','release','name','manufacturer','value']})}
    <div id="watch-grid"></div>`;
  mountFilterPanel('watch',['.fig-filter-row']);
  wireFilterBar(content,filters,()=>renderWatchlist(),()=>{state.watchFilters=Object.assign(filters,defaultWatchFilters())});
  $$('[data-list]',content).forEach(button=>button.onclick=()=>renderWatchlist(Number(button.dataset.list)));
  $('#watch-new').onclick=async()=>{
    const name=prompt('Name der neuen Liste');if(!name)return;
    try{const created=await post('/api/watchlists',{name});await refreshCounts();renderWatchlist(created.id)}catch(error){toast(error.message)}
  };
  $('#watch-rename',content)?.addEventListener('click',async()=>{
    const name=prompt('Neuer Name der Liste',list.name);if(!name||name===list.name)return;
    try{await patch(`/api/watchlists/${list.id}`,{name});await refreshCounts();renderWatchlist(list.id)}catch(error){toast(error.message)}
  });
  $('#watch-delete',content)?.addEventListener('click',async()=>{
    if(!confirm(`Liste „${list.name}“ mit ${plural(stats.count,'Figur','Figuren')} löschen?`))return;
    try{await del(`/api/watchlists/${list.id}`);await refreshCounts();renderWatchlist(defaultListId())}catch(error){toast(error.message)}
  });
  renderFigureGrid($('#watch-grid'),data.figures,{
    tile:figure=>figureTile(figure,{
      badge:figure.target_reached?'<span class="fig-mark reached" title="Marktwert am oder unter dem Zielpreis">Ziel ✓</span>':'',
      note:[figure.target_price!=null?`Ziel ${money(figure.target_price)}`:'',figure.note].filter(Boolean).map(escapeHtml).join(' · ')}),
    empty:stats.count?'<div class="empty-state"><b>Keine Figur passt zu den Filtern</b></div>':'<div class="empty-state"><b>Die Liste ist leer</b><span>Setze Figuren mit dem Herz im Katalog auf deine Wunschliste.</span><button type="button" class="primary-button" data-route-catalog>Zum Katalog</button></div>'});
  $('[data-route-catalog]',content)?.addEventListener('click',()=>routeTo('catalog'));
}

// ---- Preorders ----------------------------------------------------------------------------------

const PREORDER_TABS=[['open','Offen'],['delivered','Angekommen'],['cancelled','Storniert'],['all','Alle']];

function preorderGroups(rows){
  const month=thisMonth(),groups=new Map();
  for(const row of rows){
    const open=['ordered','paid','shipped'].includes(row.status);
    let key,label;
    if(!open){key=`z-${row.status}`;label=statusLabel(row.status)}
    else if(!row.expected_release){key='y-none';label='Ohne Termin'}
    else if(row.expected_release.slice(0,7)<month){key='0-overdue';label='Überfällig'}
    else{key=`1-${row.expected_release.slice(0,7)}`;label=row.expected_release.slice(0,7)===month?`Diesen Monat · ${partialDate(row.expected_release.slice(0,7))}`:partialDate(row.expected_release.slice(0,7))}
    if(!groups.has(key))groups.set(key,{label,rows:[]});
    groups.get(key).rows.push(row);
  }
  return [...groups.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([,group])=>group);
}

function preorderRow(row){
  const open=['ordered','paid','shipped'].includes(row.status);
  const money_=[row.total!=null?money(row.total):'Preis offen',row.paid?`bezahlt ${money(row.paid)}`:'',row.outstanding?`<b class="fig-outstanding">offen ${money(row.outstanding)}</b>`:''].filter(Boolean).join(' · ');
  return `<div class="fig-preorder" data-preorder="${row.id}">
    <img class="fig-preorder-art" loading="lazy" src="${figureThumb(row)}" alt="" data-open-figure="${row.figure_id}">
    <div class="fig-preorder-main">
      <b data-open-figure="${row.figure_id}">${escapeHtml(row.figure_name)}</b>
      <small>${escapeHtml([row.shop,row.order_number&&`#${row.order_number}`,row.quantity>1&&`${row.quantity} Stück`,row.ordered_at&&`bestellt ${partialDate(row.ordered_at)}`].filter(Boolean).join(' · '))}</small>
      <small>${money_}${row.delays?` · <span class="fig-delay">${row.delays}× verschoben</span>`:''}${row.tracking?` · Sendung ${escapeHtml(row.tracking)}`:''}${row.delivered_at?` · angekommen ${partialDate(row.delivered_at)}`:''}</small>
    </div>
    <div class="fig-preorder-side">
      <select class="select-control status-select status-${row.status}" data-status="${row.id}" aria-label="Status">${Object.entries(state.boot.statuses).map(([key,label])=>`<option value="${key}" ${row.status===key?'selected':''}>${escapeHtml(label)}</option>`).join('')}</select>
      ${open?`<span class="fig-expected">${escapeHtml(partialDate(row.expected_release)||'kein Termin')}</span>`:''}
      <button type="button" class="icon-button" data-edit-preorder="${row.id}" title="Bearbeiten">✎</button>
    </div>
  </div>`;
}

async function renderPreorders(){
  const stale=renderGuard();
  if(!$('#preorder-list'))content.innerHTML=loader('Vorbestellungen werden geladen …');
  let data;
  try{data=await api(`/api/preorders?status=${state.preorderStatus}`)}catch(error){if(!stale())content.innerHTML=`<div class="empty-state"><b>Vorbestellungen nicht erreichbar</b><span>${escapeHtml(error.message)}</span></div>`;return}
  if(stale())return;
  const stats=data.stats;
  content.innerHTML=`${pageHead({eyebrow:'VORBESTELLUNGEN',title:'Vorbestellungen',text:'Was bestellt ist, was noch zu zahlen ist und wann es kommen soll.',
      actions:'<a class="secondary-button" href="/api/export/preorders.csv">CSV</a><button type="button" class="primary-button" id="preorder-new">＋ Vorbestellen</button>'})}
    ${statPill([
      {label:'Offen',value:stats.open},{label:'Noch zu zahlen',value:money(stats.outstanding),className:stats.outstanding?'missing':''},
      {label:'Diesen Monat',value:stats.due_this_month},{label:'Überfällig',value:stats.overdue,className:stats.overdue?'missing':''},
    ],{className:'fig-summary',columns:4,mobileColumns:2})}
    <div class="segmented fig-modes fig-preorder-tabs">${PREORDER_TABS.map(([key,label])=>`<button type="button" data-preorder-tab="${key}" class="${state.preorderStatus===key?'active':''}">${label}${key==='delivered'&&stats.delivered?` <small>${stats.delivered}</small>`:''}${key==='cancelled'&&stats.cancelled?` <small>${stats.cancelled}</small>`:''}</button>`).join('')}</div>
    <div id="preorder-list">${data.preorders.length?preorderGroups(data.preorders).map(group=>`<section class="fig-preorder-group"><h2>${escapeHtml(group.label)} <small>${group.rows.length}</small></h2>${group.rows.map(preorderRow).join('')}</section>`).join('')
      :`<div class="empty-state"><b>${state.preorderStatus==='open'?'Keine offenen Vorbestellungen':'Nichts in dieser Ansicht'}</b><span>Vorbestellen kannst du jede Figur aus ihrem Dialog oder über „＋ Vorbestellen“.</span></div>`}</div>`;
  $$('[data-preorder-tab]',content).forEach(button=>button.onclick=()=>{state.preorderStatus=button.dataset.preorderTab;renderPreorders()});
  $('#preorder-new').onclick=()=>pickFigure('Welche Figur möchtest du vorbestellen?',figure=>openPreorderDialog(figure));
  $$('[data-open-figure]',content).forEach(element=>element.onclick=()=>openFigure(Number(element.dataset.openFigure),'preorders'));
  $$('[data-edit-preorder]',content).forEach(button=>button.onclick=()=>{
    const row=data.preorders.find(item=>item.id===Number(button.dataset.editPreorder));
    openPreorderDialog({id:row.figure_id,name:row.figure_name,release_date:row.figure_release},row);
  });
  $$('[data-status]',content).forEach(select=>select.onchange=async()=>{
    try{
      await patch(`/api/preorders/${select.dataset.status}`,{status:select.value});
      toast(select.value==='delivered'?'Angekommen – in die Sammlung gebucht':`Status: ${statusLabel(select.value)}`);
      refreshCounts();renderPreorders();
    }catch(error){toast(error.message)}
  });
}

// A small search to pick a figure for something (a new preorder): the quick search's results.
function pickFigure(title,onPick){
  const modal=openDialog({id:'pick-figure',eyebrow:'FIGUR WÄHLEN',title,body:`<input class="dl-control" id="pick-query" placeholder="Name, Serie, Hersteller …" autocomplete="off"><div id="pick-results" class="fig-pick-results"><p class="muted">Tippe mindestens zwei Zeichen.</p></div>`});
  let timer,sequence=0;
  $('#pick-query',modal).oninput=event=>{clearTimeout(timer);timer=setTimeout(async()=>{
    const q=event.target.value.trim(),mine=++sequence,results=$('#pick-results',modal);
    if(q.length<2){results.innerHTML='<p class="muted">Tippe mindestens zwei Zeichen.</p>';return}
    const rows=await api(`/api/search?q=${encodeURIComponent(q)}&limit=20`).catch(()=>[]);
    if(mine!==sequence)return;
    results.innerHTML=rows.length?rows.map(row=>`<button type="button" class="search-result" data-pick="${row.id}"><img class="search-thumb fig-search-thumb" src="${figureThumb(row)}" alt=""><div><b>${escapeHtml(row.name)}</b><small>${escapeHtml(figureSubtitle(row))}</small></div></button>`).join('')
      :`<p class="muted">Nichts gefunden. <button type="button" class="link-button" id="pick-create">„${escapeHtml(q)}“ anlegen</button></p>`;
    $$('[data-pick]',results).forEach(button=>button.onclick=()=>{const row=rows.find(item=>item.id===Number(button.dataset.pick));closeDialog();onPick(row)});
    $('#pick-create',results)?.addEventListener('click',()=>{closeDialog();openFigureForm({name:q})});
  },220)};
}
