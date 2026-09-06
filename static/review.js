/* Persistent batches: one video in memory, independent reviewed revisions on disk. */
(() => {
  const t = (zh,en) => UI.language === 'en' ? en : zh;
  const fields = ['video','video_clips','product_name','subtitles','speech_segments','sound_markers','visual','asr_quality','settings','model_output'];
  const signature = value => JSON.stringify(Object.fromEntries(fields.map(key=>[key,value[key]])));
  const sameVideo = (a,b) => String(a||'').replaceAll('\\','/').toLowerCase() === String(b||'').replaceAll('\\','/').toLowerCase();
  let items=[], batches=[], batch=localStorage.getItem('smartPackaging.review.batch')||'', selected=new Set(), baseline=signature(state), saving=null, switching=false, refreshing=false, saveBlocked=false, initialized=false;
  let search='', filter='all', feedback='';
  const current = () => items.find(item=>sameVideo(item.video,state.video));
  const dirty = () => Boolean(state.video) && signature(state)!==baseline;
  const originalPost = post;
  post = async (url,data) => {
    const saved = url==='/api/save' ? {video:data.video, signature:signature(data)} : null;
    const result=await originalPost(url,data);
    if(saved && sameVideo(state.video,saved.video)) {
      state.revision=result.revision;
      baseline=saved.signature;
    }
    return result;
  };
  async function saveCurrent(force=false) {
    if(saving) await saving;
    if(!state.video) return;
    pullSettings();
    if(!force && !dirty()) return;
    const snapshot=JSON.parse(JSON.stringify(state));
    saving=post('/api/save',snapshot);
    try {await saving;saveBlocked=false;} finally {saving=null;}
  }
  const originalLoad=load;
  load=async()=>{
    if(switching) return false;
    const target=$('#path').value.trim();
    switching=true;
    try {
      await saveCurrent();
      $('#path').value=target;
      const loaded=await originalLoad();
      if(loaded===false) return false;
      pullSettings();baseline=signature(state);saveBlocked=false;
      localStorage.setItem('smartPackaging.review.lastVideo',state.video);
      renderList();return true;
    } catch(error) {status(error.message);$('#path').value=state.video;return false;}
    finally {switching=false;}
  };
  $('#load').onclick=()=>load();
  async function openItem(item) {
    if(switching)return;
    $('#path').value=item.video;
    await load();
  }
  const pending = item => ['queued','processing'].includes(item.processing);
  const exporting = item => ['queued','exporting'].includes(item.export_status);
  function label(item) {
    if(item.processing==='error') return t('包装失败','Analysis failed');
    if(item.processing==='queued') return t('等待包装','Queued for analysis');
    if(item.processing==='processing') return t('包装中','Analyzing');
    if(item.export_status==='error') return t('导出失败','Export failed');
    if(item.export_status==='queued') return t('等待导出','Queued for export');
    if(item.export_status==='exporting') return t('导出中','Exporting');
    if(item.export_current) return t('已导出','Exported');
    if(item.reviewed) return t('已审阅','Reviewed');
    return item.ready ? t('待审阅','Awaiting review') : t('待包装','Awaiting analysis');
  }
  const scoped = () => items.filter(item=>!batch||(item.batches||[]).includes(batch));
  function filtered() {
    return scoped().filter(item=>(item.name+' '+item.folder).toLowerCase().includes(search.toLowerCase()))
      .filter(item=>filter==='all'||(filter==='pending'&&!item.reviewed&&!item.export_current)
        ||(filter==='approved'&&item.reviewed)||(filter==='exported'&&item.export_current)
        ||(filter==='error'&&(item.processing==='error'||item.export_status==='error')));
  }
  function renderList() {
    const shown=filtered(), active=current();
    const scope=scoped();
    $('#reviewSummary').textContent=t(`共 ${scope.length} 条 · 已审阅 ${scope.filter(i=>i.reviewed).length} · 已导出 ${scope.filter(i=>i.export_current).length}`,
      `${scope.length} videos · ${scope.filter(i=>i.reviewed).length} reviewed · ${scope.filter(i=>i.export_current).length} exported`);
    $('#reviewFeedback').textContent=feedback;
    $('#reviewList').innerHTML=shown.length ? shown.map(item=>{
      const color=exporting(item)||pending(item)?'working':item.export_status==='error'||item.processing==='error'?'failed':item.reviewed?'complete':'waiting';
      return `<article class="review-card ${active?.id===item.id?'current':''}" data-id="${esc(item.id)}">
        <input class="review-check" type="checkbox" aria-label="${esc(t('选择 ','Select ')+item.name)}" ${selected.has(item.id)?'checked':''}>
        <button class="review-open" title="${esc(item.video)}"><strong>${esc(item.name)}</strong><small>${esc(item.folder)}</small></button>
        <div class="review-meta"><span class="review-badge ${color}">${esc(label(item))}</span><span>${item.subtitle_count||0} ${t('条字幕','captions')}</span>${item.quality_status==='needs_review'?`<span class="review-warning">${t('需回听','Listen to flagged regions')}</span>`:''}</div>
        ${item.error||item.export_error?`<div class="review-error">${esc(item.export_error||item.error)}</div>`:''}
        ${item.output?`<div class="review-output" title="${esc(item.output)}">${esc(t('成片：','Output: ')+item.output)}${item.exported_revision&&!item.export_current?' · '+t('当前修改尚未导出','New edits not exported'):''}</div>`:''}
      </article>`;
    }).join('') : `<div class="review-empty"><b>${t('把剪好的视频加入这里','Add your edited videos here')}</b><p>${t('选择文件夹 → 智能包装 → 逐条审阅 → 单个或批量导出。','Choose a folder → Analyze → Review each video → Export one or a batch.')}</p><p>${t('关闭软件后，列表和已保存的修改仍会保留。','The list and saved edits persist after closing.')}</p></div>`;
    $('#reviewList').querySelectorAll('.review-card').forEach(card=>{
      const item=items.find(i=>i.id===card.dataset.id);
      card.querySelector('.review-check').onchange=e=>{e.target.checked?selected.add(item.id):selected.delete(item.id);updateButtons();};
      card.querySelector('.review-open').onclick=()=>openItem(item);
    });
    $('#reviewCurrent').textContent=active?label(active):t('逐条审阅字幕','Review captions one video at a time');
    updateButtons();
  }
  function updateButtons() {
    const scope=scoped(), chosen=scope.filter(i=>selected.has(i.id)), active=current();
    $('#reviewAnalyze').disabled=!(chosen.length?chosen:scope).some(i=>!i.ready&&!pending(i)&&!exporting(i));
    $('#reviewExportSelected').disabled=!chosen.length||chosen.some(i=>!i.reviewed||pending(i)||exporting(i));
    $('#reviewExportAll').disabled=!scope.length||scope.some(i=>!i.reviewed||pending(i)||exporting(i));
    $('#reviewRemove').disabled=!chosen.length||chosen.some(i=>pending(i)||exporting(i));
    $('#reviewComplete').disabled=!active?.ready||pending(active)||switching;
    $('#reviewPrevious').disabled=!active||scope.indexOf(active)<=0;
    $('#reviewNext').disabled=!active||scope.indexOf(active)<0||scope.indexOf(active)>=scope.length-1;
    $('#reviewSelectedCount').textContent=t(`已选 ${chosen.length}`,`${chosen.length} selected`);
  }
  function buildPanel() {
    $('#batch').textContent=t('待审阅列表','Review queue');
    $('#render').textContent=t('导出当前','Export current');
    $('#reviewTab').textContent=t('待审阅','Review');
    $('#reviewPane').innerHTML=`<select id="reviewBatch" class="review-batch" aria-label="${t('选择批次','Choose batch')}"></select><div id="reviewSummary" class="review-summary"></div>
      <div class="review-import"><input id="reviewFolder" aria-label="${t('视频文件夹','Video folder')}" placeholder="${t('粘贴剪好视频的文件夹路径','Paste a folder of edited videos')}"><div class="review-actions"><button id="reviewPick">${t('选择文件夹','Choose folder')}</button><button id="reviewImport">${t('加入列表','Add folder')}</button><label><input type="checkbox" id="reviewRecursive">${t('含子文件夹','Subfolders')}</label></div></div>
      <div class="review-actions"><button id="reviewAnalyze" class="primary">${t('批量智能包装','Analyze batch')}</button><button id="reviewExportAll">${t('全部导出','Export all')}</button></div>
      <div class="review-actions"><button id="reviewExportSelected">${t('导出所选','Export selected')}</button><button id="reviewRemove">${t('移出所选','Remove selected')}</button></div>
      <div class="review-search"><input id="reviewSearch" aria-label="${t('搜索待审阅视频','Search review queue')}" placeholder="${t('搜索视频名称','Search videos')}" value="${esc(search)}"><select id="reviewFilter" aria-label="${t('筛选审阅状态','Filter review status')}"><option value="all">${t('全部状态','All statuses')}</option><option value="pending">${t('待处理 / 待审阅','Pending / review')}</option><option value="approved">${t('已审阅','Reviewed')}</option><option value="exported">${t('已导出','Exported')}</option><option value="error">${t('失败','Failed')}</option></select></div>
      <div class="review-select"><label><input id="reviewSelectAll" type="checkbox">${t('全选当前列表','Select visible')}</label><span id="reviewSelectedCount"></span></div>
      <div id="reviewFeedback" class="review-feedback" role="status"></div><div id="reviewList"></div>`;
    $('#reviewBar').innerHTML=`<span id="reviewCurrent"></span><div><button id="reviewPrevious">${t('上一条','Previous')}</button><button id="reviewComplete" class="primary">${t('审阅完成 · 下一条','Reviewed · Next')}</button><button id="reviewNext">${t('下一条','Next')}</button></div>`;
    $('#reviewFilter').value=filter;
    $('#reviewSearch').oninput=e=>{search=e.target.value;renderList();};
    $('#reviewFilter').onchange=e=>{filter=e.target.value;renderList();};
    $('#reviewSelectAll').onchange=e=>{filtered().forEach(i=>e.target.checked?selected.add(i.id):selected.delete(i.id));renderList();};
    $('#reviewPick').onclick=()=>action(async()=>{const picked=await get('/api/pick-folder?ui_language='+UI.language);if(picked.folder){$('#reviewFolder').value=picked.folder;await importFolder();}});
    $('#reviewImport').onclick=()=>action(importFolder);
    $('#reviewAnalyze').onclick=()=>action(analyzeBatch);
    $('#reviewExportSelected').onclick=()=>action(()=>exportItems(scoped().filter(i=>selected.has(i.id))));
    $('#reviewExportAll').onclick=()=>action(()=>exportItems(scoped()));
    $('#reviewRemove').onclick=()=>action(async()=>{await saveCurrent();await post('/api/review/remove',{ids:[...selected]});selected.clear();await refresh();});
    $('#reviewComplete').onclick=()=>action(()=>complete(true));
    $('#reviewPrevious').onclick=()=>openItem(scoped()[scoped().indexOf(current())-1]);
    $('#reviewNext').onclick=()=>openItem(scoped()[scoped().indexOf(current())+1]);
    $('#reviewBatch').onchange=e=>{batch=e.target.value;selected.clear();localStorage.setItem('smartPackaging.review.batch',batch);renderList();};
    renderBatches();
    renderList();
  }
  function renderBatches() {
    if(batch&&!batches.some(b=>b.id===batch))batch='';
    const options=`<option value="">${t('全部批次 / 已有工程','All batches / existing projects')}</option>`+batches.slice().reverse().map(b=>`<option value="${esc(b.id)}">${esc(b.name+' · '+new Date(b.added_at*1000).toLocaleString())}</option>`).join('');
    if($('#reviewBatch').innerHTML!==options)$('#reviewBatch').innerHTML=options;
    $('#reviewBatch').value=batch;
  }
  async function action(fn) {
    try {await fn();} catch(error) {feedback=UI.message(error.message);status(error.message);renderList();}
  }
  async function importFolder() {
    const folder=$('#reviewFolder').value.trim();
    if(!folder)throw Error(t('请先选择或填写视频文件夹','Choose or enter a video folder first'));
    await saveCurrent();
    const result=await post('/api/review/import',{folder,recursive:$('#reviewRecursive').checked});
    batch=result.batch_id;localStorage.setItem('smartPackaging.review.batch',batch);
    selected=new Set(result.ids);feedback=t(`已加入 ${result.count} 个视频。点击“批量智能包装”开始。`,`Added ${result.count} videos. Click Analyze batch to begin.`);
    await refresh();
  }
  async function analyzeBatch() {
    await saveCurrent();
    const ids=selected.size?[...selected]:scoped().map(i=>i.id);
    const result=await post('/api/review/analyze',{ids,language:$('#asrLanguage').value});
    feedback=t(`已安排 ${result.count} 个视频，按顺序包装；已有字幕工程会保留。`,`${result.count} videos queued for sequential analysis. Existing caption projects are preserved.`);
    await refresh();
  }
  async function complete(next=false) {
    await saveCurrent(true);await refresh();
    const active=current();if(!active)throw Error(t('请先载入视频','Load a video first'));
    await post('/api/review/approve',{id:active.id,revision:state.revision});
    feedback=t('已保存并标记审阅完成','Saved and marked as reviewed');
    await refresh();
    if(next){const scope=scoped(),at=scope.findIndex(i=>i.id===active.id), ordered=[...scope.slice(at+1),...scope.slice(0,at)];const target=ordered.find(i=>i.ready&&!i.reviewed&&!pending(i));if(target)await openItem(target);}
  }
  async function exportItems(rows) {
    await saveCurrent();await refresh();
    const ids=rows.map(i=>i.id);
    const result=await post('/api/review/export',{ids});
    feedback=t(`已加入导出队列：${result.count} 个。可继续审阅其他视频。`,`Queued ${result.count} exports. You can continue reviewing other videos.`);
    await refresh();
  }
  async function refresh() {
    if(refreshing)return;
    refreshing=true;
    try {
      const previous=current(), response=await get('/api/review');items=response.items;batches=response.batches||[];
      renderBatches();
      selected=new Set([...selected].filter(id=>items.some(i=>i.id===id)));
      const active=current();
      // Never replace another video's editor when a background worker finishes.
      if(previous&&pending(previous)&&active?.ready&&!pending(active)&&!switching&&!dirty()) {
        $('#path').value=active.video;await load();
      }
      renderList();
      if(!initialized){initialized=true;const last=localStorage.getItem('smartPackaging.review.lastVideo');const resume=items.find(i=>sameVideo(i.video,last));if(!state.video&&resume)await openItem(resume);}
    } finally {refreshing=false;}
  }
  $('#batch').onclick=()=>{$('#reviewTab').click();action(refresh);};
  $('#save').onclick=()=>action(async()=>{await saveCurrent(true);feedback=t('当前工程已保存','Current project saved');await refresh();status('工程和训练快照已保存',0);});
  $('#render').onclick=()=>action(async()=>{await complete();await exportItems([current()]);});
  $('#auto').onclick=()=>action(async()=>{
    if(!state.video)throw Error(t('请先载入视频','Load a video first'));
    if(state.subtitles.length&&!window.confirm(t('重新智能包装会替换当前视频的字幕和音效，继续吗？','Re-analyzing replaces this video’s captions and effects. Continue?')))return;
    await saveCurrent();
    await post('/api/start-auto',{video:state.video,language:$('#asrLanguage').value,video_clips:currentClips()});
    await refresh();$('#reviewTab').click();
  });
  window.addEventListener('beforeunload',event=>{if(dirty()||saving){event.preventDefault();event.returnValue='';}});
  $('#uiLanguage').addEventListener('change',()=>buildPanel());
  buildPanel();$('#reviewTab').click();action(refresh);
  setInterval(async()=>{
    if(switching||saving)return;
    try {
      if(state.video&&!pending(current()||{})) {
        pullSettings();
        if(dirty()&&!saveBlocked) {
          try {await saveCurrent();} catch(error){saveBlocked=true;feedback=UI.message(error.message);status(error.message);}
        }
      }
      await refresh();
    } catch(error) {feedback=UI.message(error.message);renderList();}
  },2500);
  window.ReviewDesk={saveCurrent,refresh,hasUnsavedChanges:dirty};
})();
