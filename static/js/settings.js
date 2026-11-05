// A user's settings and account.

function closeAccountPasswordDialog(){
  $('#account-password-modal')?.remove();
  document.documentElement.style.overflow='';
  document.body.style.overflow='';
}

function openAccountPasswordDialog(user){
  closeAccountPasswordDialog();
  const modal=document.createElement('div');
  modal.id='account-password-modal';
  modal.className='overlay account-password-overlay';
  modal.setAttribute('role','dialog');
  modal.setAttribute('aria-modal','true');
  modal.setAttribute('aria-labelledby','account-password-dialog-title');
  modal.innerHTML=`<div class="utility-dialog account-password-dialog">
    <div class="dialog-head account-password-dialog-head"><div><span class="eyebrow">SICHERHEIT</span><h2 id="account-password-dialog-title">${user.password_set?'Passwort ändern':'Passwort festlegen'}</h2><p>${user.password_set?'Bestätige zuerst dein aktuelles Passwort.':'Lege ein Passwort für die lokale Anmeldung fest.'}</p></div><button class="close-button" type="button" data-password-dialog-close aria-label="Dialog schließen">×</button></div>
    <div class="account-password-fields">
      ${user.password_set?`<label><span>Aktuelles Passwort</span><input id="account-current-password" type="password" autocomplete="current-password"></label>`:''}
      <label><span>Neues Passwort</span><input id="account-new-password" type="password" autocomplete="new-password"></label>
      <label><span>Neues Passwort bestätigen</span><input id="account-confirm-password" type="password" autocomplete="new-password"></label>
    </div>
    <div class="dialog-actions account-password-actions"><button class="secondary-button" type="button" data-password-dialog-close>Abbrechen</button><span class="spacer"></span><button class="primary-button" type="button" id="account-password-save">${user.password_set?'Passwort ändern':'Passwort festlegen'}</button></div>
  </div>`;
  document.body.append(modal);
  document.documentElement.style.overflow='hidden';
  document.body.style.overflow='hidden';
  $$('[data-password-dialog-close]',modal).forEach(button=>button.onclick=closeAccountPasswordDialog);
  modal.onmousedown=event=>{if(event.target===modal)closeAccountPasswordDialog()};
  $('#account-password-save',modal).onclick=async event=>{
    const newPassword=$('#account-new-password',modal).value,confirmPassword=$('#account-confirm-password',modal).value;
    if(newPassword!==confirmPassword){toast('Die Passwörter stimmen nicht überein.');return}
    const button=event.currentTarget;
    button.disabled=true;
    try{
      await post('/api/account/password',{new_password:newPassword,current_password:$('#account-current-password',modal)?.value||''});
      state.boot.user.password_set=true;
      closeAccountPasswordDialog();
      renderSettings();
      toast('Passwort gespeichert');
    }catch(error){button.disabled=false;toast(error.message)}
  };
  requestAnimationFrame(()=>$(user.password_set?'#account-current-password':'#account-new-password',modal)?.focus());
}

function renderSettings(){
  const appearance=appearancePreference();
  const user=state.boot.user,oauth=state.boot.oauth||{enabled:false};
  content.innerHTML=`<div class="page-head compact-page-head user-settings-page-head"><div><span class="eyebrow">KONTO</span><h1>Einstellungen</h1><p>Dein Konto, die Darstellung und was du teilst.</p></div></div>
    <div class="user-settings-layout">
    <section class="settings-section user-settings-card settings-card-profile settings-card-wide">
      <div class="user-settings-card-head"><span class="user-settings-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M4.8 20c1.3-3.6 4.2-5.5 7.2-5.5s5.9 1.9 7.2 5.5"/></svg></span><div><span class="eyebrow">KONTO</span><h2>Konto</h2><p>Profil und Anmeldung dieses Kontos.</p></div></div>
      <div class="settings-grid settings-grid-account">
        <label class="settings-field"><span>Anzeigename</span><input id="account-display-name" value="${escapeHtml(user.display_name)}"></label>
        <label class="settings-field"><span>Benutzername</span><input id="account-username" value="${escapeHtml(user.username)}"></label>
        <label class="settings-field"><span>E-Mail</span><input id="account-email" type="email" placeholder="name@example.com" value="${escapeHtml(user.email||'')}"></label>
      </div>
      <div class="account-sign-in">
        <div class="account-sign-in-row"><div><b>Passwort</b><small>${user.password_set?'Die Anmeldung mit Benutzername und Passwort ist aktiv.':'Noch kein lokales Passwort festgelegt.'}</small></div><span class="user-settings-status ${user.password_set?'is-connected':''}"><i></i>${user.password_set?'Aktiv':'Keins'}</span><button class="secondary-button" type="button" id="account-password-open">${user.password_set?'Passwort ändern':'Passwort festlegen'}</button></div>
        ${oauth.enabled?`<div class="account-sign-in-row"><div><b>Single Sign-On</b><small>${user.oauth_linked?`Dieses Konto ist mit ${escapeHtml(oauth.provider_name)} verbunden.`:`Verknüpfe dein Konto mit ${escapeHtml(oauth.provider_name)}.`}</small></div><span class="user-settings-status ${user.oauth_linked?'is-connected':''}"><i></i>${user.oauth_linked?'Verbunden':'Nicht verbunden'}</span>${user.oauth_linked?`<button class="secondary-button" id="account-oauth-unlink">Verbindung trennen</button>`:`<a class="secondary-button" href="/oauth/login">Mit ${escapeHtml(oauth.provider_name)} verbinden</a>`}</div>`:''}
      </div>
      <div class="user-settings-actions account-settings-actions"><span class="spacer"></span><button class="primary-button" id="account-save"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>Kontodaten speichern</button></div>
    </section>
    <section class="settings-section user-settings-card settings-card-appearance settings-card-wide">
      <div class="user-settings-card-head"><span class="user-settings-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 9 9c0-1-.8-1.5-1.7-1.2a4 4 0 0 1-5.1-5.1C14.5 4.8 14 4 13 4l-1-.1Z"/><circle cx="7.5" cy="12" r=".7"/><circle cx="10" cy="17" r=".7"/></svg></span><div><span class="eyebrow">OBERFLÄCHE</span><h2>Darstellung</h2><p>Wähle die Farbgebung der Oberfläche. „Auto“ folgt der Einstellung deines Systems.</p></div></div>
      <div class="appearance-settings-grid">
        <div class="segmented mobile-appearance-toggle">${[['light','Hell'],['dark','Dunkel'],['auto','Auto']].map(([value,label])=>`<button type="button" data-mobile-appearance="${value}" class="${appearance===value?'active':''}">${label}</button>`).join('')}</div>
      </div>
    </section>
    <section class="settings-section user-settings-card settings-card-wide">
      <div class="user-settings-card-head"><span class="user-settings-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M7 3h10v18l-5-4-5 4z"/></svg></span><div><span class="eyebrow">LINK-IMPORT</span><h2>Lesezeichen „Zu Ophir Figures“</h2><p>Viele Figurenseiten (MyFigureCollection, AmiAmi, Kotobukiya …) lassen den Server nicht lesen. Das Lesezeichen liest die Produktseite, die du gerade offen hast, in deinem eigenen Browser und öffnet hier das Formular mit den Daten.</p></div></div>
      <div class="fig-bookmarklet-row"><a class="primary-button fig-bookmarklet" href="${bookmarkletHref()}" title="In die Lesezeichenleiste ziehen" onclick="event.preventDefault();toast('Zieh den Knopf in deine Lesezeichenleiste und klick ihn dann auf einer Produktseite an.')">★ Zu Ophir Figures</a><span class="muted">In die Lesezeichenleiste ziehen. Auf einer Produktseite anklicken – fertig.</span></div>
    </section>
    <section class="settings-section user-settings-card settings-card-public settings-card-wide" id="public-profile-card">
      <div class="user-settings-card-head"><span class="user-settings-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg></span><div><span class="eyebrow">TEILEN</span><h2>Öffentliches Profil</h2><p>Ein Link, über den andere deine Sammlung ohne Anmeldung ansehen: deine Figuren mit Bild und Anzahl – ohne Preise, Werte, Shops, Aufbewahrungsorte und Vorbestellungen.</p></div></div>
      <div id="public-profile-body"><div class="page-loader compact"><span></span></div></div>
    </section>
    </div>`;
  renderPublicProfileSettings();
  $('#account-save',content).onclick=async()=>{
    const payload={display_name:$('#account-display-name').value.trim(),username:$('#account-username').value.trim(),email:$('#account-email').value.trim()};
    try{
      const updated=await api('/api/account',{method:'PATCH',body:JSON.stringify(payload)});
      state.boot.user={...state.boot.user,...updated};
      $('#user-name').textContent=updated.display_name; $('#user-avatar').textContent=initials(updated.display_name);
      toast('Kontodaten gespeichert');
    }catch(error){toast(error.message)}
  };
  $('#account-password-open',content).onclick=()=>openAccountPasswordDialog(user);
  $('#account-oauth-unlink',content)?.addEventListener('click',async()=>{
    try{
      await post('/api/account/oauth/unlink',{});
      state.boot.user.oauth_linked=false;
      toast('SSO-Verbindung getrennt');
      renderSettings();
    }catch(error){toast(error.message)}
  });
  $$('[data-mobile-appearance]',content).forEach(b=>b.onclick=async()=>{
    const value=b.dataset.mobileAppearance;
    await post('/api/settings',{mobileThemeAppearance:value});
    state.boot.settings.mobileThemeAppearance=value;
    applyAppearance();
    renderSettings();
    toast('Darstellung gespeichert');
  });
}

// The public profile (ophir_figures/public_profile.py): on/off, its address, the name shown and
// whether the wishlist is shared too. Saved on its own, as the address has to be checked for being free.
async function renderPublicProfileSettings(){
  const body=$('#public-profile-body',content);if(!body)return;
  let profile;
  try{profile=await api('/api/account/public-profile')}catch(error){body.innerHTML=`<p class="muted settings-hint">${escapeHtml(error.message)}</p>`;return}
  if(!body.isConnected)return;
  const user=state.boot.user;
  const draw=()=>{
    body.innerHTML=`<div class="settings-checklist">
        <label class="checkbox-row highlight-setting public-profile-switch"><span><b>Profil öffentlich</b><small>${profile.enabled&&profile.url?`Erreichbar unter <a href="${escapeHtml(profile.url)}" target="_blank" rel="noopener">${escapeHtml(profile.url)}</a>`:'Aus: niemand ohne Anmeldung sieht etwas.'}</small></span><input type="checkbox" id="public-enabled" ${profile.enabled?'checked':''}><i aria-hidden="true"></i></label>
      </div>
      <div class="settings-grid settings-grid-account">
        <label class="settings-field"><span>Adresse</span><input id="public-slug" placeholder="z. B. ${escapeHtml((user.username||'sammlung').toLowerCase().replace(/[^a-z0-9-]/g,''))}" value="${escapeHtml(profile.slug)}" autocomplete="off" spellcheck="false"></label>
        <label class="settings-field"><span>Angezeigter Name</span><input id="public-name" placeholder="${escapeHtml(user.display_name)}" value="${escapeHtml(profile.name)}" maxlength="60"></label>
      </div>
      <p class="muted settings-hint">Darstellung für Besucher</p>
      <div class="segmented public-profile-theme">${[['auto','Automatisch'],['light','Hell'],['dark','Dunkel']].map(([value,label])=>`<button type="button" data-public-theme="${value}" class="${profile.theme===value?'active':''}" aria-pressed="${profile.theme===value}">${label}</button>`).join('')}</div>
      <div class="settings-checklist"><label class="checkbox-row highlight-setting"><span><b>Wunschliste mit zeigen</b><small>Die Standard-Wunschliste, ohne Zielpreise und Notizen.</small></span><input type="checkbox" id="public-wishlist" ${profile.show_wishlist?'checked':''}><i aria-hidden="true"></i></label></div>
      <div class="user-settings-actions">${profile.url?`<button class="secondary-button" type="button" id="public-copy">Link kopieren</button>`:''}<span class="spacer"></span><button class="primary-button" type="button" id="public-save">Profil speichern</button></div>`;
    $('#public-save',body).onclick=async()=>{
      try{
        profile=await api('/api/account/public-profile',{method:'PUT',body:JSON.stringify({enabled:$('#public-enabled',body).checked,slug:$('#public-slug',body).value,name:$('#public-name',body).value,
          show_wishlist:$('#public-wishlist',body).checked,
          theme:$('[data-public-theme].active',body)?.dataset.publicTheme||'auto'})});
        toast(profile.enabled?'Profil ist öffentlich':'Profil gespeichert – nicht öffentlich');draw();
      }catch(error){toast(error.message)}
    };
    $$('[data-public-theme]',body).forEach(button=>button.onclick=()=>$$('[data-public-theme]',body).forEach(item=>{const on=item===button;item.classList.toggle('active',on);item.setAttribute('aria-pressed',String(on))}));
    $('#public-copy',body)?.addEventListener('click',async()=>{
      try{await navigator.clipboard.writeText(profile.url);toast('Link kopiert')}catch{toast(profile.url)}
    });
  };
  draw();
}
