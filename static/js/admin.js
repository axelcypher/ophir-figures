// Admin: accounts, single sign-on and tidying the shared catalogue.

async function renderAdmin(){
  const stale=renderGuard();
  content.innerHTML='<div class="page-loader"><span></span><p>Admin-Bereich wird geladen …</p></div>';
  const [oauth,users]=await Promise.all([api('/api/admin/oauth'),api('/api/admin/users')]);
  if(stale())return;
  const oauthLocked=oauth.source==='file'||oauth.source==='environment',ro=oauthLocked?'disabled':'';
  // Shared sign-in of the Ophir apps: as a slave, accounts and SSO are managed by the master.
  const byMaster=state.boot.auth?.mode==='slave';
  content.innerHTML=`<div class="page-head compact-page-head"><div><span class="eyebrow">VERWALTUNG</span><h1>Admin</h1><p>Benutzer, Anmeldung und der gemeinsame Katalog.</p></div></div>
    ${byMaster?'':`<details class="settings-section oauth-admin-card ${oauthLocked?'is-locked':''}">
      <summary class="oauth-admin-summary">
        <div class="oauth-admin-head">
          <div class="oauth-admin-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 2.8 20 6v5.2c0 4.8-3.2 8.3-8 10-4.8-1.7-8-5.2-8-10V6l8-3.2Z"/><circle cx="12" cy="10" r="2.2"/><path d="M12 12.2v4"/></svg></div>
          <div class="oauth-admin-title"><span>AUTHENTIFIZIERUNG</span><h2>Single Sign-On</h2><p>OAuth 2.0 und OpenID Connect für einen externen Identity Provider.</p></div>
          <div class="oauth-admin-state"><span class="oauth-status ${oauth.enabled?'is-active':'is-inactive'}"><i></i>${oauth.enabled?'Aktiv':'Inaktiv'}</span><span class="oauth-source-badge">${oauth.source==='file'?'Config-Datei':oauth.source==='environment'?'Umgebungsvariablen':'In der App'}</span></div>
          <span class="oauth-collapse-icon" aria-hidden="true"><svg viewBox="0 0 20 20"><path d="m5 7.5 5 5 5-5"/></svg></span>
        </div>
      </summary>
      <div class="oauth-admin-body">
      ${oauthLocked?`<div class="oauth-lock-notice"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="3"/><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10"/></svg><div><b>Konfiguration schreibgeschützt</b><span>${oauth.source==='environment'?'Die Werte kommen aus den Umgebungsvariablen <code>OAUTH_*</code> des Servers. Änderungen werden nach einem Neustart des Containers übernommen.':`Die Werte kommen aus <code>${escapeHtml(oauth.config_path)}</code>. Änderungen erfolgen in der Datei und werden nach einem Container-Neustart übernommen.`}</span></div></div>`:''}
      <div class="admin-form oauth-admin-form">
        <label class="oauth-toggle-row">
          <span class="oauth-toggle-copy"><b>SSO-Anmeldung</b><small>${oauth.enabled?'Der externe Login wird auf der Anmeldeseite angeboten.':'Die lokale Anmeldung bleibt aktiv; SSO ist derzeit ausgeblendet.'}</small></span>
          <span class="oauth-toggle-control"><input type="checkbox" id="oauth-enabled" ${oauth.enabled?'checked':''} ${ro}><span aria-hidden="true"></span></span>
        </label>

        <div class="oauth-form-group">
          <div class="oauth-form-group-head"><span>01</span><div><b>Identity Provider</b><small>Bezeichnung und Zugangsdaten der registrierten Anwendung.</small></div></div>
          <div class="admin-form-grid oauth-provider-grid">
            <label class="oauth-field"><span>Button-Beschriftung</span><input id="oauth-provider-name" value="${escapeHtml(oauth.provider_name||'')}" placeholder="z. B. Mit Authentik anmelden" ${ro}></label>
            <label class="oauth-field"><span>Client-ID</span><input id="oauth-client-id" value="${escapeHtml(oauth.client_id||'')}" autocomplete="off" ${ro}></label>
            <label class="oauth-field"><span>Client-Secret</span><input id="oauth-client-secret" type="password" autocomplete="new-password" placeholder="${oauth.client_secret_set?'••••••••  ·  leer lassen zum Beibehalten':'Client-Secret'}" ${ro}></label>
            <label class="oauth-field oauth-field-wide"><span>Discovery-URL <em>empfohlen</em></span><input id="oauth-discovery-url" value="${escapeHtml(oauth.discovery_url||'')}" placeholder="https://idp.example.com/.well-known/openid-configuration" ${ro}></label>
          </div>
        </div>

        <div class="oauth-form-group">
          <div class="oauth-form-group-head"><span>02</span><div><b>Manuelle Endpunkte</b><small>Nur erforderlich, wenn der Provider keine Discovery-URL bereitstellt.</small></div></div>
          <div class="admin-form-grid oauth-endpoint-grid">
            <label class="oauth-field"><span>Autorisierung</span><input id="oauth-authorize-url" value="${escapeHtml(oauth.authorize_url||'')}" placeholder="https://…/authorize" ${ro}></label>
            <label class="oauth-field"><span>Token</span><input id="oauth-token-url" value="${escapeHtml(oauth.token_url||'')}" placeholder="https://…/token" ${ro}></label>
            <label class="oauth-field"><span>Userinfo</span><input id="oauth-userinfo-url" value="${escapeHtml(oauth.userinfo_url||'')}" placeholder="https://…/userinfo" ${ro}></label>
          </div>
        </div>

        <div class="oauth-form-group">
          <div class="oauth-form-group-head"><span>03</span><div><b>Identität und Konten</b><small>Scopes, Claims und Verhalten bei der ersten Anmeldung.</small></div></div>
          <div class="admin-form-grid oauth-claims-grid">
            <label class="oauth-field oauth-field-wide"><span>Scopes</span><input id="oauth-scopes" value="${escapeHtml(oauth.scopes||'')}" placeholder="openid email profile" ${ro}></label>
            <label class="oauth-field"><span>Benutzername-Claim</span><input id="oauth-username-claim" value="${escapeHtml(oauth.username_claim||'')}" ${ro}></label>
            <label class="oauth-field"><span>E-Mail-Claim</span><input id="oauth-email-claim" value="${escapeHtml(oauth.email_claim||'')}" ${ro}></label>
            <label class="oauth-field"><span>Subjekt-ID-Claim</span><input id="oauth-subject-claim" value="${escapeHtml(oauth.subject_claim||'')}" ${ro}></label>
            <label class="oauth-field oauth-field-wide"><span>Konto-Zuordnung</span><select id="oauth-account-matching" class="select-control" ${ro}>
              <option value="manual" ${oauth.account_matching==='manual'?'selected':''}>Nur manuelle Verknüpfung</option>
              <option value="email" ${oauth.account_matching==='email'?'selected':''}>Automatisch über identische, vom Provider bestätigte E-Mail-Adresse verknüpfen</option>
              <option value="auto_provision" ${oauth.account_matching==='auto_provision'?'selected':''}>Neue Konten automatisch anlegen</option>
            </select></label>
          </div>
        </div>

        <div class="oauth-admin-actions"><span>Die Anmeldung mit Benutzername und Passwort bleibt zusätzlich verfügbar.</span>${oauthLocked?'':`<button class="primary-button" id="oauth-save"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>SSO-Einstellungen speichern</button>`}</div>
      </div>
      </div>
    </details>`}
    <section class="settings-section admin-settings-card">
      <div class="user-settings-card-head admin-settings-card-head"><span class="user-settings-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.4"/><path d="M2.8 20c.5-3.6 3-5.6 6.2-5.6s5.700 2 6.200 5.600M16 5.200a3.200 3.200 0 0 1 0 6M18.200 14.800c1.800.700 2.800 2.400 3 5.200"/></svg></span><div><span class="eyebrow">ZUGANG</span><h2>Benutzer</h2><p>Konten anlegen, Rollen vergeben, Passwörter zurücksetzen.</p></div></div>
      <div class="admin-table">${users.map(u=>`<div class="admin-row" data-user-row="${u.id}">
        <div class="admin-row-head"><b>${escapeHtml(u.display_name)}${u.is_self?' <span class="muted">(du)</span>':''}</b><span class="muted">${escapeHtml(u.username)}${u.email?` · ${escapeHtml(u.email)}`:''} · ${plural(u.copies,'Exemplar','Exemplare')} ·${plural(u.preorders,'offene Vorbestellung','offene Vorbestellungen')}</span></div>
        <div class="admin-status"><span class="admin-status-badge status-${u.role==='admin'?'ok':'none'}">${u.role==='admin'?'Admin':'Benutzer'}</span><span class="muted">${u.oauth_linked?'SSO verknüpft':'kein SSO'}${u.password_set?'':' · kein Passwort'}</span></div>
        ${byMaster?'':`<div class="admin-row-actions">
          <button class="secondary-button" data-edit-user="${u.id}">Bearbeiten</button>
          ${u.is_self?'':`<button class="icon-button" data-delete-user="${u.id}" data-user-name="${escapeHtml(u.username)}" title="Konto löschen">✕</button>`}
        </div>
        <div class="admin-config-editor hidden" data-user-editor="${u.id}">
          <div class="admin-form-grid admin-user-fields">
            <label>Anzeigename<input data-user-field="display_name" value="${escapeHtml(u.display_name)}"></label>
            <label>Benutzername<input data-user-field="username" value="${escapeHtml(u.username)}"></label>
            <label>E-Mail<input data-user-field="email" type="email" value="${escapeHtml(u.email)}"></label>
            <label>Rolle<select data-user-field="role" class="select-control"><option value="user" ${u.role==='user'?'selected':''}>Benutzer</option><option value="admin" ${u.role==='admin'?'selected':''}>Admin</option></select></label>
            <label>Neues Passwort<input data-user-field="password" type="password" autocomplete="new-password" placeholder="leer lassen = unverändert"></label>
            ${u.oauth_linked?`<label class="radio-label"><input type="checkbox" data-user-field="unlink_oauth"> SSO-Verknüpfung lösen</label>`:''}
          </div>
          <button class="primary-button" data-save-user="${u.id}">Speichern</button>
        </div>`}
      </div>`).join('')}</div>
      ${byMaster?`<p class="muted settings-hint">Die Konten kommen aus der Ophir-App, die die Anmeldung übernimmt: Wer sich dort anmeldet, bekommt hier beim ersten Besuch ein Konto mit Name, E-Mail und Rolle von dort. Anlegen, Ändern und Löschen geschieht dort.</p>`:`<details class="admin-add"><summary>+ Neues Konto anlegen</summary>
        <div class="admin-form admin-user-fields">
          <label>Benutzername<input id="admin-new-user-name" autocomplete="off" placeholder="3–32 Zeichen"></label>
          <label>Anzeigename<input id="admin-new-user-display" placeholder="optional"></label>
          <label>E-Mail<input id="admin-new-user-email" type="email" placeholder="optional, für SSO-Zuordnung"></label>
          <label>Passwort<input id="admin-new-user-password" type="password" autocomplete="new-password" placeholder="mindestens 8 Zeichen"></label>
          <label>Rolle<select id="admin-new-user-role" class="select-control"><option value="user">Benutzer</option><option value="admin">Admin</option></select></label>
          <button class="primary-button" id="admin-create-user">Konto anlegen</button>
        </div>
      </details>`}
    </section>
    <section class="settings-section admin-settings-card" id="admin-catalog-card">
      <div class="user-settings-card-head admin-settings-card-head"><span class="user-settings-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 4h11v16H8z"/><path d="M5 7v13h11"/><path d="M11 8h5M11 12h5"/></svg></span><div><span class="eyebrow">KATALOG</span><h2>Katalog aufräumen</h2><p>Doppelte Einträge zusammenführen und Figuren löschen, die niemand verwendet.</p></div></div>
      <div id="admin-catalog-body"><div class="page-loader compact"><span></span></div></div>
    </section>
    `;
  $('#oauth-save',content)?.addEventListener('click',async()=>{
    const payload={
      enabled:$('#oauth-enabled').checked,
      provider_name:$('#oauth-provider-name').value.trim(),
      client_id:$('#oauth-client-id').value.trim(),
      client_secret:$('#oauth-client-secret').value,
      discovery_url:$('#oauth-discovery-url').value.trim(),
      authorize_url:$('#oauth-authorize-url').value.trim(),
      token_url:$('#oauth-token-url').value.trim(),
      userinfo_url:$('#oauth-userinfo-url').value.trim(),
      scopes:$('#oauth-scopes').value.trim(),
      username_claim:$('#oauth-username-claim').value.trim(),
      email_claim:$('#oauth-email-claim').value.trim(),
      subject_claim:$('#oauth-subject-claim').value.trim(),
      account_matching:$('#oauth-account-matching').value,
    };
    try{await post('/api/admin/oauth',payload);toast('SSO-Einstellungen gespeichert');renderAdmin()}
    catch(error){toast(error.message)}
  });
  $$('[data-edit-user]',content).forEach(button=>button.onclick=()=>$(`[data-user-editor="${button.dataset.editUser}"]`,content).classList.toggle('hidden'));
  $$('[data-save-user]',content).forEach(button=>button.onclick=async()=>{
    const editor=$(`[data-user-editor="${button.dataset.saveUser}"]`,content),payload={};
    $$('[data-user-field]',editor).forEach(field=>{
      if(field.type==='checkbox'){if(field.checked)payload[field.dataset.userField]=true}
      else if(field.dataset.userField!=='password'||field.value)payload[field.dataset.userField]=field.value;
    });
    try{await api(`/api/admin/users/${button.dataset.saveUser}`,{method:'PATCH',body:JSON.stringify(payload)});toast('Konto gespeichert');renderAdmin()}
    catch(error){toast(error.message)}
  });
  $$('[data-delete-user]',content).forEach(button=>button.onclick=async()=>{
    if(!confirm(`Konto „${button.dataset.userName}“ mit Sammlung, Vorbestellungen und Wunschlisten endgültig löschen? Angelegte Katalogeinträge bleiben.`))return;
    try{await api(`/api/admin/users/${button.dataset.deleteUser}`,{method:'DELETE'});toast('Konto gelöscht');renderAdmin()}
    catch(error){toast(error.message)}
  });
  if($('#admin-create-user'))$('#admin-create-user').onclick=async()=>{
    try{
      await post('/api/admin/users',{username:$('#admin-new-user-name').value,display_name:$('#admin-new-user-display').value,email:$('#admin-new-user-email').value,password:$('#admin-new-user-password').value,role:$('#admin-new-user-role').value});
      toast('Konto angelegt');renderAdmin();
    }catch(error){toast(error.message)}
  };
  renderAdminCatalog();
}

async function renderAdminCatalog(){
  const body=$('#admin-catalog-body');if(!body)return;
  let data;
  try{data=await api('/api/admin/catalog')}catch(error){body.innerHTML=`<p class="muted">${escapeHtml(error.message)}</p>`;return}
  if(!$('#admin-catalog-body'))return;
  const byId=Object.fromEntries(data.figures.map(figure=>[figure.id,figure]));
  const usage=figure=>[figure.owners&&`${figure.owners}× in Sammlungen`,figure.preorders&&`${figure.preorders}× vorbestellt`,figure.wished&&`${figure.wished}× gewünscht`].filter(Boolean).join(' · ')||'unbenutzt';
  const row=figure=>`<span class="admin-figure"><b>${escapeHtml(figure.name)}</b><small>#${figure.id} · ${escapeHtml(figure.manufacturer||'ohne Hersteller')}${figure.edition?` · ${escapeHtml(figure.edition)}`:''}${figure.jan?` · JAN ${escapeHtml(figure.jan)}`:''} · ${usage(figure)}</small></span>`;
  body.innerHTML=`<p class="muted">${data.figures.length} Figuren im Katalog · ${data.duplicates.length} mögliche Duplikate · ${data.unused.length} unbenutzt</p>
    ${data.duplicates.length?`<div class="admin-table">${data.duplicates.map(ids=>`<div class="admin-row admin-duplicate">${ids.map(id=>`<label class="admin-duplicate-option"><input type="radio" name="keep-${ids.join('-')}" value="${id}" ${id===ids[0]?'checked':''}>${row(byId[id])}</label>`).join('')}<div class="admin-row-actions"><button class="secondary-button" data-merge="${ids.join(',')}">In die gewählte zusammenführen</button></div></div>`).join('')}</div>`:'<p class="muted">Keine Duplikate gefunden.</p>'}
    ${data.unused.length?`<details class="admin-add"><summary>Unbenutzte Figuren (${data.unused.length})</summary><div class="admin-table">${data.unused.map(id=>`<div class="admin-row">${row(byId[id])}<div class="admin-row-actions"><button class="icon-button" data-delete-figure="${id}" title="Aus dem Katalog löschen">✕</button></div></div>`).join('')}</div></details>`:''}`;
  $$('[data-merge]',body).forEach(button=>button.onclick=async()=>{
    const ids=button.dataset.merge.split(',').map(Number);
    const target=Number($(`input[name="keep-${ids.join('-')}"]:checked`,body).value);
    if(!confirm(`${ids.length-1} Eintrag/Einträge in „${byId[target].name}“ zusammenführen? Sammlungen, Vorbestellungen, Wunschlisten und Marktwerte ziehen mit um.`))return;
    try{for(const source of ids.filter(id=>id!==target))await post('/api/admin/catalog/merge',{source,target});toast('Zusammengeführt');renderAdminCatalog()}
    catch(error){toast(error.message)}
  });
  $$('[data-delete-figure]',body).forEach(button=>button.onclick=async()=>{
    if(!confirm(`„${byId[button.dataset.deleteFigure].name}“ aus dem Katalog löschen?`))return;
    try{await api(`/api/admin/catalog/${button.dataset.deleteFigure}`,{method:'DELETE'});toast('Gelöscht');renderAdminCatalog()}
    catch(error){toast(error.message)}
  });
}
