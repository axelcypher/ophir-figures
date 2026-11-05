// Import / export: restoring a JSON backup (preview, apply, undo) and the downloads.

let backupData=null;

function setIeMode(mode){
  $$('.importexport-toggle button').forEach(button=>button.classList.toggle('active',button.dataset.ieMode===mode));
  $('#importexport-import-section').classList.toggle('hidden',mode!=='import');
  $('#importexport-export-section').classList.toggle('hidden',mode!=='export');
  $('#importexport-title').textContent=mode==='import'?'Sicherung wiederherstellen':'Exportieren';
}

function openImportExport(mode='export'){
  backupData=null;
  $('#import-json-file').value='';
  $('#import-preview').innerHTML='';
  $('#apply-import').disabled=true;
  setIeMode(mode);
  openOverlay('import-modal');
}

async function handleBackupFile(file){
  backupData=null;$('#apply-import').disabled=true;
  const preview=$('#import-preview');
  if(!file){preview.innerHTML='';return}
  try{backupData=JSON.parse(await file.text())}catch{preview.innerHTML='<div class="fig-import-note warning"><b>Keine gültige JSON-Datei</b></div>';return}
  try{
    const result=await post('/api/import/json/preview',{data:backupData});
    preview.innerHTML=`<div class="fig-import-note ok"><b>Sicherung${result.user?` von ${escapeHtml(result.user)}`:''}${result.exported_at?` vom ${date(result.exported_at)}`:''}</b>
      <span>${plural(result.figures,'Figur','Figuren')}, davon ${result.figures_new} neu für den Katalog · ${plural(result.collection,'Sammlungseintrag','Sammlungseinträge')} · ${plural(result.preorders,'Vorbestellung','Vorbestellungen')} · ${plural(result.watchlist_entries,'Wunschlisteneintrag','Wunschlisteneinträge')} in ${plural(result.watchlists,'Liste','Listen')}</span></div>`;
    $('#apply-import').disabled=false;
  }catch(error){backupData=null;preview.innerHTML=`<div class="fig-import-note warning"><b>Nicht lesbar</b><span>${escapeHtml(error.message)}</span></div>`}
}

async function applyBackup(){
  if(!backupData)return;
  const button=$('#apply-import'),label=button.textContent;
  button.disabled=true;button.textContent='Wird wiederhergestellt …';
  try{
    const strategy=$('input[name="strategy"]:checked').value;
    const result=await post('/api/import/json/apply',{data:backupData,strategy});
    closeOverlay('import-modal');
    const parts=[plural(result.collection,'Sammlungseintrag','Sammlungseinträge'),plural(result.preorders,'Vorbestellung','Vorbestellungen'),plural(result.watchlist_entries,'Wunschlisteneintrag','Wunschlisteneinträge'),result.figures_created&&`${result.figures_created} neue Figuren im Katalog`].filter(Boolean);
    toast(`Wiederhergestellt: ${parts.join(' · ')}`,'Rückgängig',async()=>{await post(`/api/import/${result.operation_id}/undo`,{});toast('Wiederherstellung rückgängig gemacht');await refreshCounts();refreshCurrentView()});
    await refreshCounts();refreshCurrentView();
  }catch(error){toast(error.message)}
  finally{button.disabled=false;button.textContent=label}
}

function wireImportExport(){
  $$('.importexport-toggle button').forEach(button=>button.onclick=()=>setIeMode(button.dataset.ieMode));
  $('#import-json-file').onchange=event=>handleBackupFile(event.target.files[0]);
  $('#apply-import').onclick=applyBackup;
}
