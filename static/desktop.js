/* Desktop-only integration. Ordinary browser tabs keep their existing behavior. */
(() => {
  if (!window.chrome?.webview) return;
  const fields = ['video', 'video_clips', 'product_name', 'subtitles', 'speech_segments',
    'sound_markers', 'visual', 'asr_quality', 'settings', 'model_output'];
  const signature = value => JSON.stringify(Object.fromEntries(fields.map(key => [key, value[key]])));
  let baseline = signature(state), loaded = 0, busy = 0, lastTitle = '';
  const originalPost = post;
  post = async (url, data) => {
    const saved = ['/api/save', '/api/render'].includes(url) ? signature(data) : null;
    if (url === '/api/render') busy++;
    try {
      const result = await originalPost(url, data);
      if (url === '/api/load') loaded++;
      if (saved !== null) baseline = saved;
      return result;
    } finally { if (url === '/api/render') busy--; }
  };
  const originalLoad = load;
  load = async () => {
    const revision = loaded;
    await originalLoad();
    if (loaded !== revision) {
      pullSettings();
      baseline = signature(state);
      localStorage.setItem('smartPackaging.desktop.lastVideo', state.video);
      updateTitle();
    }
  };
  $('#load').onclick = load;
  const dirty = () => Boolean(state.video) && signature(state) !== baseline;
  function updateTitle() {
    const name = state.video ? state.video.split(/[\\/]/).pop() : '';
    const title = (UI.language === 'en' ? 'Smart Video Packaging' : '剪辑智能包装') +
      (name ? ' — ' + name : '') + (dirty() ? ' *' : '');
    if (title !== lastTitle) {
      window.chrome.webview.postMessage({type: 'title', title});
      lastTitle = title;
    }
  }
  window.DesktopShell = {
    hasUnsavedChanges() { if (state.video) pullSettings(); return dirty(); },
    isExporting() { return busy > 0; },
    async saveForClose() {
      try {
        pullSettings();
        await post('/api/save', state);
        status('工程和训练快照已保存', 0);
        updateTitle();
        return true;
      } catch (error) { status(error.message, 0); return false; }
    }
  };
  document.addEventListener('keydown', event => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    const button = {s: '#save', o: '#pick', e: '#render'}[event.key.toLowerCase()];
    if (button) { event.preventDefault(); if (!$('#'+button.slice(1)).disabled) $(button).click(); }
  });
  // Restore the last path, without loading/overwriting a saved project automatically.
  const lastVideo = localStorage.getItem('smartPackaging.desktop.lastVideo');
  if (lastVideo) $('#path').value = lastVideo;
  updateTitle();
  setInterval(updateTitle, 1200);
})();
