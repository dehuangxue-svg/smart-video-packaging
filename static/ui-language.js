// UI translations only. Subtitle text, filenames and project data stay untouched.
const UI = (() => {
  const storageKey = 'smartPackaging.uiLanguage';
  let language = 'zh';
  try { language = localStorage.getItem(storageKey) === 'en' ? 'en' : 'zh'; } catch {}
  const en = {
    '视频剪辑':'Video editing', ' 个片段':' clips', '撤销':'Undo', '重做':'Redo', '删除选中片段':'Delete selected clip',
    '单击 V1 选择视频；S 分割，Delete 删除。拖动片段两端可裁剪。':'Select a V1 clip. Press S to split or Delete to remove. Drag its edges to trim.',
    '裁剪范围（原视频秒）':'Trim range (source seconds)', '入点':'In point', '出点':'Out point', '应用裁剪':'Apply trim',
    '裁掉播放头之前':'Trim before playhead', '裁掉播放头之后':'Trim after playhead',
    '剪辑操作已恢复':'Edit restored', '请把播放头放在片段内部':'Place the playhead inside the clip',
    '视频已分割':'Video split', '请选择视频片段':'Select a video clip', '片段至少保留一帧':'Keep at least one frame',
    '请选择要删除的片段':'Select a clip to delete', '已删除选中片段':'Selected clip deleted',
    '时间轴没有视频片段':'The timeline has no video clips', '视频片段范围无效':'Invalid source clip range',
    '已删除并接合；跨剪辑边界的字幕请回听':'Removed and joined; review subtitles crossing the cut',
    '已删除并接合，字幕和音效已同步':'Removed and joined; subtitles and sounds moved with the video',
    '已裁剪；跨剪辑边界的字幕请回听':'Trimmed; review subtitles crossing the cut',
    '视频已裁剪，字幕和音效已同步':'Video trimmed; subtitles and sounds moved with the video',
    '正在准备剪辑后的视频':'Preparing the edited video',
    '剪辑智能包装':'Smart Video Packaging', '剪':'✂', '自动包装与字幕精修':'Automatic styling and subtitle editing',
    '拖入视频或输入视频完整路径':'Enter the full path to a video', '选择':'Browse', '载入':'Load',
    '▦ 批量':'▦ Batch', '✦ 智能包装':'✦ Auto style', '保存':'Save', '导出':'Export',
    '界面语言':'Interface language', '可用功能':'Tools', '媒体':'Media', '音频':'Audio', '文本':'Text', '调节':'Adjust',
    '添加字幕':'Add subtitle', '播放头位置':'At playhead', '默认字幕':'Default subtitle',
    '在当前播放头创建 2 秒字幕片段':'Create a 2-second subtitle at the playhead', '添加到播放头':'Add at playhead',
    '添加后会自动选中 T1 片段，并在右侧“当前字幕”中进入文字编辑。':'Select a T1 clip to edit its text in the Subtitle panel on the right.',
    '设为开始':'Set start', '设为结束':'Set end', '分割':'Split', '合并':'Merge', '删除':'Delete', '删':'×',
    '选':'Select', '开始':'Start', '结束':'End', '字幕文字':'Subtitle text', '高亮词':'Highlights', '用':'Use',
    '音效库':'Sound library', '29 种 · CC0':'29 sounds · CC0', ' 种 · CC0':' sounds · CC0',
    '＋ 添加所选音效':'+ Add selected sound',
    '专业素材音效，可商用。拖到 A1 可添加；拖片段主体移动时间，拖右边缘调整时长。播放时会同步试听并在触发时亮起。':'Commercial-use sounds. Drag to A1 to add, drag a clip to move it, or drag its right edge to change duration. Clips light up as they play.',
    '时间':'Time', '音效':'Sound', '音量':'Volume', '试听':'Preview', '⌕ 匹配当前产品素材':'⌕ Find product assets',
    '高光素材不放在 Hook，也不覆盖主播手持带字板的画面。视频素材保留原直播音轨。':'Keep product footage outside the hook and away from shots of the host holding a text board. Preserve the original speech audio.',
    '播放器':'Player', '上一边界':'Previous boundary', '下一边界':'Next boundary', '播放/暂停':'Play / pause',
    '静音':'Mute', '取消静音':'Unmute', '全屏':'Full screen', '请载入已经精剪完成的视频':'Load an edited video to get started',
    '当前字幕':'Subtitle', '未选择':'None selected',
    '在左侧添加字幕，或单击 T1 时间轴中的字幕片段。':'Add a subtitle on the left, or select a clip on the T1 track.',
    '项目信息':'Project', '基础':'Basic', '产品名称':'Product name', '来自文件名':'From filename',
    '原声语言':'Speech language', '识别字幕':'Transcription', '自动识别':'Auto detect', '普通话':'Mandarin',
    '英语':'English', '粤语':'Cantonese', '日语':'Japanese', '韩语':'Korean',
    '字幕样式':'Subtitle style', '实时预览':'Live preview', '字体':'Font', '正在读取…':'Loading…',
    '产品字幕预览':'Subtitle preview', '字幕预览':'Subtitle preview', '产品':'Product', ' 款可选':' fonts available',
    '字号':'Font size', '横向位置':'Horizontal position', '纵向位置':'Vertical position',
    '0 上 / 100 下':'0 top / 100 bottom', '字幕颜色':'Text color', '高亮颜色':'Highlight color',
    '声音':'Audio', 'A1 音效轨':'A1 sound track', '音效总音量':'Master sound volume', '默认 50%':'Default 50%',
    '当前音效':'Sound clip', '单击或拖动 A1 轨道上的音效。':'Select or drag a sound clip on the A1 track.',
    '识别质检':'ASR quality', '未运行':'Not run', '智能包装后显示语音覆盖率与时间戳状态。':'Speech coverage and timestamp checks appear after auto styling.',
    '导出设置':'Export settings', '本地输出':'Local output', '字幕与音效同步导出':'Export with subtitles and sound effects', 'H.264 视频 · AAC 原直播音轨':'H.264 video · AAC original audio',
    '字幕、音效与高光包装同步导出':'Export video with subtitles and sound effects',
    '时间轴':'Timeline', '在播放头分割':'Split at playhead', '删除选中字幕':'Delete selected subtitle',
    '拖动片段和边缘可精修时间':'Drag clips or edges to adjust timing', '跳到开头':'Go to start',
    '上一个边界':'Previous boundary', '下一个边界':'Next boundary', '吸附':'Snap', '跟随':'Follow',
    '缩放':'Zoom', '适应':'Fit', '时间刻度':'Time ruler', '主视频':'Video', '字幕':'Subtitles',
    'A1 音效轨道':'A1 sound track', '主视频 · 原声':'Video · Original audio',
    '输入字幕文字':'Enter subtitle text', '开始/秒':'Start / s', '结束/秒':'End / s', '逗号分隔':'Comma-separated',
    '启用字幕':'Enable subtitle', '删除片段':'Delete clip', '音效类型':'Sound type', '当前音效类型':'Current sound type',
    '当前音效时间':'Sound start time', '时长/秒':'Duration / s', '当前音效时长':'Sound duration',
    '片段音量':'Clip volume', '当前音效音量':'Sound clip volume', '启用音效':'Enable sound',
    '试听；也可拖到 A1 轨道':'Preview or drag to the A1 track', '拖动调整音效时长':'Drag to adjust sound duration',
    '通过':'Passed', '需回听':'Review needed', '● 逐字时间戳':'● Token timestamps', '○ 旧时间算法':'○ Estimated timing',
    '● 覆盖率 ':'● Coverage ', '语音段 ':'Speech segments ', '局部重试 ':'Local retries ', ' 秒':' s', '秒':'s',
    '载入视频后显示时间轴':'Load a video to show its timeline', '没有找到同名素材目录':'No matching product folder found',
    '匹配目录：':'Matching folders: ', '本地与高光素材':'Local and product assets',
    '轻弹':'Pop', '闪光':'Sparkle', '轻转场':'Light whoosh', '点击':'Click', '轻敲':'Tap', '提示铃':'Bell',
    '清脆和弦':'Chime', '金币':'Coin', '完成提示':'Success', '弹跳':'Bounce', '脆响':'Snap', '低频强调':'Bass impact',
    '清脆叮':'Ding', '水滴':'Water drop', '气泡':'Bubble', '滑动':'Swipe', '快速呼啸':'Fast whoosh',
    '柔和呼啸':'Soft whoosh', '上升揭晓':'Riser', '魔法闪现':'Magic', '相机快门':'Camera shutter',
    '键盘输入':'Typing', '收银提示':'Cash register', '鼓点':'Drum hit', '爆炸冲击':'Boom', '错误提示':'Error',
    '心跳':'Heartbeat', '掌声':'Applause', '惊讶提示':'Surprise', '强调':'Emphasis', '重点':'Accent',
    '转场':'Transition', '节奏':'Rhythm', '提示':'Notification', '价格':'Price', '活泼':'Playful',
    '自然':'Nature', '氛围':'Atmosphere', '生活':'Everyday', '综艺':'Entertainment',
    '价格信息':'Price cue', '操作提示':'Action cue', '产品细节':'Product detail', '效果强调':'Benefit cue',
    '组合或收尾':'Bundle or closing cue', '重点强调':'Key point', '惊喜强调':'Surprise cue', '节奏强调':'Rhythm cue',
    '人工添加':'Manually added', '拖入音效':'Dragged sound', '人工新建字幕':'Manually added subtitle',
    '正在读取视频…':'Loading video…', '请先载入视频':'Please load a video first', '正在启动…':'Starting…',
    '正在建立批量队列…':'Creating batch queue…', '工程和训练快照已保存':'Project and training snapshot saved',
    '正在低内存模式导出…':'Exporting in low-memory mode…', '已删除音效片段':'Sound clip deleted',
    '播放头已在视频末尾，请向前移动后添加':'Move the playhead back from the end before adding a subtitle',
    '请选择一条字幕':'Select a subtitle', '播放位置不在该字幕内':'The playhead is outside this subtitle',
    '至少选择两行':'Select at least two subtitles', '输入字幕':'Enter subtitle',
    '正在用SenseVoice识别字幕':'Transcribing with SenseVoice', '正在识别功效、卖点和高亮词':'Analyzing benefits, selling points and highlights',
    '正在抽帧检查主播和文字板风险':'Checking sampled frames for the host and text boards',
    '识别完成，存在需回听的语音区间':'Transcription complete; some speech segments need review',
    '自动分析完成，时间戳质检通过':'Auto styling complete; timestamp checks passed',
    '存在未解决的硬规则问题':'Resolve the following issues before exporting',
    '视频时长无效，请重新载入有效视频':'Invalid video duration; load a valid video',
    'Hook结束时间必须在3–10秒之间':'The hook must end between 3 and 10 seconds',
    '字幕字号必须在16–160之间':'Subtitle font size must be between 16 and 160',
    'Hook内没有识别到功效或明确卖点':'No benefit or selling point was detected in the hook',
    '最后一句疑似没有说完，请回听并调整结束点':'The last sentence may be incomplete; review its ending',
    '所选文件夹中没有可处理的视频':'No supported videos found in the selected folder',
    '音效不存在':'Sound not found', '任务不存在':'Job not found'
  };
  const escapeRegex = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const phrases = new RegExp(Object.keys(en).sort((a,b)=>b.length-a.length).map(escapeRegex).join('|'), 'g');
  const t = text => language === 'en' ? (en[text] ?? text) : text;
  // Translate authored template chunks, never interpolated content.
  const fragment = text => language === 'en' ? text.replace(phrases, key => en[key]) : text;
  const html = (parts,...values) => parts.reduce((out,part,i)=>out+fragment(part)+(i<values.length?values[i]:''),'');
  const patterns = [
    [/^已载入 (.+) 秒 · (.+)$/, (a,b)=>`Loaded ${a} s · ${b}`],
    [/^已加入 (\d+) 个视频$/, n=>`Queued ${n} videos`],
    [/^批量完成：(\d+)\/(\d+)，需回听(\d+)，失败(\d+)$/, (a,b,c,d)=>`Batch complete: ${a}/${b}; review ${c}; failed ${d}`],
    [/^已在 (.+) 添加字幕$/, at=>`Subtitle added at ${at}`],
    [/^音效时长 (.+) 秒$/, n=>`Sound duration: ${n} s`],
    [/^音效移动到 (.+)$/, at=>`Sound moved to ${at}`],
    [/^字幕 ([\d:.]+–[\d:.]+)$/, at=>`Subtitle ${at}`],
    [/^已(添加|拖入)(.+) · ([\d:.]+)$/, (action,name,at)=>`${action==='添加'?'Added':'Dropped'} ${t(name)} · ${at}`],
    [/^字幕(\d+)时间不合法：(.*)$/, (n,at)=>`Invalid timing for subtitle ${n}: ${at}`],
    [/^字幕(.+)必须在0–100%之间$/, label=>`Subtitle ${t(label)} must be between 0 and 100%`],
    [/^(人工添加|拖入音效)·(.+)$/, (action,name)=>`${t(action)} · ${t(name)}`]
  ];
  const prefixes = {'导出完成：':'Export complete: ', '视频不存在：':'Video not found: ',
    '无法导出：':'Unable to export: ', '正在处理：':'Processing: ', '无法打开选择窗口：':'Unable to open file picker: ',
    '无法打开文件夹选择窗口：':'Unable to open folder picker: ', '缺少轻量ASR模型，请先双击“下载轻量模型.bat”：':'Missing ASR models. Run the model download script: '};
  function message(value) {
    const text = String(value ?? '');
    try {
      const data=JSON.parse(text), detail=data.detail ?? data;
      if (typeof detail==='string') return message(detail);
      if (detail.message) return message(detail.message)+(detail.issues?.length?' · '+detail.issues.map(x=>message(x.message)).join(' · '):'');
      if (Array.isArray(detail)) return detail.map(x=>message(x.msg||x.message||String(x))).join(' · ');
    } catch {}
    if (language !== 'en') return text;
    if (en[text]) return en[text];
    if (text.endsWith('（使用稳定缓存）')) return message(text.slice(0,-8))+' (cached)';
    for (const [pattern,format] of patterns) { const match=text.match(pattern); if(match) return format(...match.slice(1)); }
    for (const [prefix,translation] of Object.entries(prefixes)) if(text.startsWith(prefix)) return translation+message(text.slice(prefix.length));
    return text;
  }
  function apply(root=document) {
    root.querySelectorAll('[data-ui]').forEach(el=>{el.textContent=t(el.dataset.ui)});
    for (const attr of ['title','placeholder','aria-label']) {
      root.querySelectorAll(`[data-ui-${attr}]`).forEach(el=>el.setAttribute(attr,t(el.getAttribute(`data-ui-${attr}`))));
    }
    document.documentElement.lang=language==='en'?'en':'zh-CN';
    document.title=t('剪辑智能包装');
  }
  function set(value) { language=value==='en'?'en':'zh'; try{localStorage.setItem(storageKey,language)}catch{} apply(); }
  return {t,html,message,apply,set,get language(){return language}};
})();
