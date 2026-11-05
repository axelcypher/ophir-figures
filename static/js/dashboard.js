// Dashboard: totals, upcoming releases of preorders, latest additions, categories.

async function renderDashboard(){
  const stale=renderGuard();
  const user=state.boot.user;
  content.innerHTML=`<div class="dashboard-shell"><section class="dashboard-hero"><div class="hero-top"><div class="hero-copy"><h1>Willkommen zurück, ${escapeHtml(user.display_name.split(' ')[0])}.</h1><p>Deine Vitrine auf einen Blick.</p></div></div></section>${loader('Übersicht wird geladen …')}</div>`;
  let data;
  try{data=await api('/api/dashboard')}catch(error){if(!stale())content.innerHTML=`<div class="empty-state"><b>Übersicht nicht erreichbar</b><span>${escapeHtml(error.message)}</span></div>`;return}
  if(stale())return;
  const collection=data.collection,preorders=data.preorders,counts=data.counts;
  const maxCategory=Math.max(1,...collection.by_category.map(item=>item.copies));
  content.innerHTML=`<div class="dashboard-shell">
    <section class="dashboard-hero">
      <div class="hero-top">
        <div class="hero-copy"><h1>Willkommen zurück, ${escapeHtml(user.display_name.split(' ')[0])}.</h1><p>${collection.figures?`${plural(collection.figures,'Figur','Figuren')} in deiner Sammlung${preorders.stats.open?`, ${plural(preorders.stats.open,'Vorbestellung','Vorbestellungen')} unterwegs`:''}.`:'Deine Sammlung wartet auf die erste Figur.'}</p></div>
        ${statPill([
          {label:'Sammlungswert',value:money(collection.value)},{label:'Ausgegeben',value:money(collection.spent)},
          {label:'Noch zu zahlen',value:money(preorders.stats.outstanding),className:preorders.stats.outstanding?'missing':''},
        ],{className:'dashboard-summary',columns:3,mobileColumns:3})}
      </div>
      <nav class="dashboard-quick-nav" aria-label="Schnellzugriff">
        <button type="button" data-dashboard-route="catalog"><svg viewBox="0 0 24 24"><path d="M8 4h11v16H8z"/><path d="M5 7v13h11"/></svg><span>Katalog</span><strong>${counts.catalog}</strong></button>
        <button type="button" data-dashboard-route="collection"><svg viewBox="0 0 24 24"><path d="M5 20h14M7 20V9l5-5 5 5v11"/><path d="M10 20v-5h4v5"/></svg><span>Sammlung</span><strong>${counts.collection}</strong></button>
        <button type="button" data-dashboard-route="preorders"><svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/></svg><span>Vorbestellt</span><strong>${counts.preorders}</strong></button>
        <button type="button" data-dashboard-route="watchlist"><svg viewBox="0 0 24 24"><path d="M12 20.5s-7.5-4.6-9.8-9A5.4 5.4 0 0 1 12 6a5.4 5.4 0 0 1 9.8 5.5c-2.3 4.4-9.8 9-9.8 9Z"/></svg><span>Wunschliste</span><strong>${counts.wished}</strong></button>
      </nav>
    </section>
    <div class="fig-dashboard-grid">
      <section class="settings-section fig-dashboard-card">
        <div class="fig-card-head"><h2>Demnächst</h2><button type="button" class="link-button" data-dashboard-route="preorders">Alle Vorbestellungen</button></div>
        ${preorders.upcoming.length?`<div class="fig-upcoming">${preorders.upcoming.map(row=>`<button type="button" class="fig-upcoming-row" data-open-figure="${row.figure_id}">
          <img loading="lazy" src="${figureThumb(row)}" alt=""><span><b>${escapeHtml(row.figure_name)}</b><small>${escapeHtml([row.shop,statusLabel(row.status)].filter(Boolean).join(' · '))}${row.delays?` · ${row.delays}× verschoben`:''}</small></span>
          <span class="fig-upcoming-when ${row.expected_release&&row.expected_release.slice(0,7)<thisMonth()?'overdue':''}">${escapeHtml(partialDate(row.expected_release)||'offen')}${row.outstanding?`<small>${money(row.outstanding)} offen</small>`:''}</span></button>`).join('')}</div>`
          :'<p class="muted">Keine offenen Vorbestellungen.</p>'}
      </section>
      <section class="settings-section fig-dashboard-card">
        <div class="fig-card-head"><h2>Nach Kategorie</h2></div>
        ${collection.by_category.length?`<div class="fig-bars">${collection.by_category.map(item=>`<button type="button" class="fig-bar" data-category="${escapeHtml(item.category)}"><span>${escapeHtml(item.category)}</span><i style="--share:${Math.round(item.copies/maxCategory*100)}%"></i><b>${item.copies}</b></button>`).join('')}</div>`
          :'<p class="muted">Noch keine Figuren in der Sammlung.</p>'}
      </section>
    </div>
    <section class="fig-dashboard-recent">
      <div class="fig-card-head"><h2>Zuletzt hinzugefügt</h2><button type="button" class="link-button" data-dashboard-route="collection">Zur Sammlung</button></div>
      <div id="dashboard-recent"></div>
    </section>
  </div>`;
  $$('[data-dashboard-route]',content).forEach(element=>element.onclick=()=>routeTo(element.dataset.dashboardRoute));
  $$('[data-open-figure]',content).forEach(element=>element.onclick=()=>openFigure(Number(element.dataset.openFigure),'preorders'));
  $$('[data-category]',content).forEach(element=>element.onclick=()=>{
    state.collectionFilters={...defaultCollectionFilters(),category:element.dataset.category==='Ohne Kategorie'?'':element.dataset.category};
    routeTo('collection');
  });
  renderFigureGrid($('#dashboard-recent'),collection.recent.map(item=>({...item,owned:item.quantity})),{
    empty:'<div class="empty-state"><b>Noch nichts hinzugefügt</b><span>Leg deine erste Figur an – am schnellsten mit einem Link zur Produktseite.</span><button type="button" class="primary-button" data-first-figure>＋ Figur anlegen</button></div>'});
  $('[data-first-figure]',content)?.addEventListener('click',()=>openFigureForm());
}
