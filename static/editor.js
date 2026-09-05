// Basic editing: select, split, ripple trim/delete, history and clip menus.
let editUndo=[],editRedo=[],videoTrimDrag=null;
const editFields=['video_clips','subtitles','sound_markers','settings','speech_segments','visual','asr_quality'];
function editSnapshot(){return {data:Edit.copy(Object.fromEntries(editFields.map(k=>[k,state[k]]).filter(([,v])=>v!==undefined))),time:timelineNow()}}
function recordEdit(before){
  if(JSON.stringify(before.data)===JSON.stringify(editSnapshot().data))return;
  editUndo.push(before);if(editUndo.length>30)editUndo.shift();editRedo=[];renderEditHistory();
}
function renderEditHistory(){$('#editUndo').disabled=!editUndo.length;$('#editRedo').disabled=!editRedo.length}
function initializeEditor(){
  state.video_clips=Edit.copy(currentClips());selectedVideoIndex=-1;previewClipIndex=0;previewAtEnd=false;
  editUndo=[];editRedo=[];renderEditHistory();renderVideoEditor();
}
function refreshAfterEdit(at=timelineNow()){
  video.pause();stopPreviewSfx();selectedTimelineSub=-1;selectedSfxIndex=-1;
  video.style.visibility=currentClips().length?'visible':'hidden';
  if(!currentClips().length)$('#caption').innerHTML='';
  renderAll();renderVideoEditor();seekTimeline(at);video.ontimeupdate?.();
}
function restoreEdit(from,to){
  if(!from.length)return;
  const saved=from.pop();to.push(editSnapshot());Object.assign(state,saved.data);selectedVideoIndex=-1;
  refreshAfterEdit(saved.time);renderEditHistory();status('剪辑操作已恢复');
}
$('#editUndo').onclick=()=>restoreEdit(editUndo,editRedo);
$('#editRedo').onclick=()=>restoreEdit(editRedo,editUndo);

function frameTime(value){
  const parts=String(state.media?.fps||'25/1').split('/').map(Number),fps=(parts[0]/(parts[1]||1))||25;
  return Math.round(value*fps)/fps;
}
function selectVideo(index,{seek=null}={}){
  selectedVideoIndex=index;selectedTimelineSub=-1;selectedSfxIndex=-1;
  renderSubs();renderActiveSubtitle();renderSfx();renderSfxInspector();renderTimeline();renderVideoEditor();
  if(seek!==null)seekTimeline(seek);
}
function splitVideo(){
  if(!state.video)return status('请先载入视频');
  const at=frameTime(timelineNow()),row=Edit.locate(currentClips(),at);
  const index=selectedVideoIndex>=0?selectedVideoIndex:row?.index;
  const before=editSnapshot();
  if(!Edit.split(state.video_clips,index,at))return status('请把播放头放在片段内部');
  selectedVideoIndex=index+1;recordEdit(before);refreshAfterEdit(at);status('视频已分割');
}
function deleteVideo(){
  const row=Edit.layout(currentClips())[selectedVideoIndex];
  if(!row)return status('请选择视频片段');
  const before=editSnapshot();Edit.removeRange(state,row.start,row.end,sfxNaturalDuration);
  selectedVideoIndex=Math.min(selectedVideoIndex,state.video_clips.length-1);recordEdit(before);refreshAfterEdit(row.start);
  status(state.subtitles.some(s=>s.edit_review)?'已删除并接合；跨剪辑边界的字幕请回听':'已删除并接合，字幕和音效已同步');
}
function trimVideo(index,newStart,newEnd){
  const row=Edit.layout(currentClips())[index];if(!row)return;
  newStart=Math.max(row.source_start,frameTime(newStart));newEnd=Math.min(row.source_end,frameTime(newEnd));
  if(newEnd-newStart<0.04)return status('片段至少保留一帧');
  const before=editSnapshot();
  // Remove the tail first so the head still uses the original output position.
  const tail=row.start+newEnd-row.source_start;
  if(newEnd<row.source_end-0.001)Edit.removeRange(state,tail,row.end,sfxNaturalDuration);
  if(newStart>row.source_start+0.001)Edit.removeRange(state,row.start,row.start+newStart-row.source_start,sfxNaturalDuration);
  selectedVideoIndex=Math.min(index,state.video_clips.length-1);recordEdit(before);refreshAfterEdit(row.start);
  status(state.subtitles.some(s=>s.edit_review)?'已裁剪；跨剪辑边界的字幕请回听':'视频已裁剪，字幕和音效已同步');
}
function renderVideoEditor(){
  const box=$('#videoEditor'),row=Edit.layout(currentClips())[selectedVideoIndex];
  $('#videoEditCount').textContent=ui`${currentClips().length} 个片段`;
  if(!row){box.innerHTML=ui`<div class="caption-editor-empty">单击 V1 选择视频；S 分割，Delete 删除。拖动片段两端可裁剪。</div>`;return}
  box.innerHTML=ui`<div class="small">裁剪范围（原视频秒）</div><div class="row"><div class="field"><label>入点</label><input id="videoTrimIn" type="number" step=".04" value="${row.source_start.toFixed(3)}"></div><div class="field"><label>出点</label><input id="videoTrimOut" type="number" step=".04" value="${row.source_end.toFixed(3)}"></div></div><div class="toolbar"><button id="videoApplyTrim">应用裁剪</button><button id="videoDoSplit">分割</button><button id="videoDoDelete">删除</button></div>`;
  $('#videoApplyTrim').onclick=()=>trimVideo(selectedVideoIndex,+$('#videoTrimIn').value,+$('#videoTrimOut').value);
  $('#videoDoSplit').onclick=splitVideo;$('#videoDoDelete').onclick=deleteVideo;
}
function deleteSelection(){
  if(selectedVideoIndex>=0)return deleteVideo();
  const before=editSnapshot();
  if(selectedSfxIndex>=0){state.sound_markers.splice(selectedSfxIndex,1);selectedSfxIndex=-1}
  else if(selectedTimelineSub>=0){state.subtitles.splice(selectedTimelineSub,1);selectedTimelineSub=-1}
  else return status('请选择要删除的片段');
  recordEdit(before);refreshAfterEdit(before.time);status('已删除选中片段');
}
function splitSelection(){
  if(selectedTimelineSub>=0){useTimelineSelection();$('#split').click()}
  else if(selectedSfxIndex<0)splitVideo();
}
$('#timelineSplit').onclick=splitSelection;$('#timelineDelete').onclick=deleteSelection;

// Existing subtitle/sound actions participate in the same undo stack.
for(const id of ['addSub','deleteSub','split','merge','setStart','setEnd','addSfx']){
  const button=$('#'+id),original=button.onclick;
  button.onclick=function(event){const before=editSnapshot();original.call(this,event);recordEdit(before)};
}
const originalDeleteSfx=deleteSfx;
deleteSfx=function(index){const before=editSnapshot();originalDeleteSfx(index);recordEdit(before)};
document.addEventListener('click',e=>{
  if(e.target.closest('#activeSubtitleDelete')){
    const before=editSnapshot();queueMicrotask(()=>recordEdit(before));
  }
},true);

// Video trim handles preview the boundary while dragging; one edit on release.
$('#videoLane').addEventListener('pointerdown',e=>{
  if(e.button!==0)return;
  const element=e.target.closest('.video-clip');if(!element)return;
  e.preventDefault();e.stopPropagation();
  const index=+element.dataset.index,row=Edit.layout(currentClips())[index],edge=e.target.closest('.video-trim')?.dataset.edge;
  if(!edge){selectVideo(index,{seek:timelineTimeFromEvent(e,$('#videoLane'))});return}
  video.pause();selectedVideoIndex=index;selectedTimelineSub=-1;selectedSfxIndex=-1;renderVideoEditor();
  videoTrimDrag={index,row,edge,x:e.clientX,target:element,start:row.source_start,end:row.source_end};
},true);
window.addEventListener('pointermove',e=>{
  const d=videoTrimDrag;if(!d)return;
  e.preventDefault();const delta=frameTime((e.clientX-d.x)/timelinePps),min=.04;
  if(d.edge==='left')d.start=Math.max(d.row.source_start,Math.min(d.row.source_end-min,d.row.source_start+delta));
  else d.end=Math.min(d.row.source_end,Math.max(d.row.source_start+min,d.row.source_end+delta));
  d.target.style.left=(d.row.start+d.start-d.row.source_start)*timelinePps+'px';
  d.target.style.width=Math.max(6,(d.end-d.start)*timelinePps)+'px';
  $('#videoTrimIn').value=d.start.toFixed(3);$('#videoTrimOut').value=d.end.toFixed(3);
  seekTimeline(d.row.start+(d.edge==='left'?d.start:d.end)-d.row.source_start);
},true);
window.addEventListener('pointerup',()=>{if(!videoTrimDrag)return;const d=videoTrimDrag;videoTrimDrag=null;trimVideo(d.index,d.start,d.end)},true);

let trackDragBefore=null;
$('#timelineContent').addEventListener('pointerdown',e=>{if(e.button===0&&e.target.closest('.subclip,.sfx-marker'))trackDragBefore=editSnapshot()},true);
window.addEventListener('pointerup',()=>{if(trackDragBefore){recordEdit(trackDragBefore);trackDragBefore=null}});

const contextMenu=document.createElement('div');contextMenu.id='clipContextMenu';contextMenu.className='clip-context-menu';contextMenu.setAttribute('role','menu');contextMenu.hidden=true;document.body.append(contextMenu);
function hideClipMenu(){contextMenu.hidden=true}
function openClipMenu(event,kind,index){
  event.preventDefault();hideClipMenu();
  if(kind==='video')selectVideo(index);
  if(kind==='subtitle')selectSubtitle(index,{seek:false});
  if(kind==='sound')selectSfx(index,{seek:false,open:false});
  const items=[];
  if(kind!=='sound')items.push(['split','在播放头分割','S']);
  if(kind==='video')items.push(['trimLeft','裁掉播放头之前','I'],['trimRight','裁掉播放头之后','O']);
  items.push(['delete','删除','Delete']);
  contextMenu.innerHTML=items.map(([action,label,key])=>`<button role="menuitem" data-action="${action}"><span>${esc(UI.t(label))}</span><kbd>${key}</kbd></button>`).join('');
  contextMenu.hidden=false;contextMenu.style.left=Math.max(6,Math.min(event.clientX,innerWidth-contextMenu.offsetWidth-8))+'px';contextMenu.style.top=Math.max(6,Math.min(event.clientY,innerHeight-contextMenu.offsetHeight-8))+'px';
  contextMenu.querySelector('button').focus();
}
document.addEventListener('contextmenu',event=>{
  const videoClip=event.target.closest('.video-clip'),sub=event.target.closest('.subclip, #subs tr'),sound=event.target.closest('.sfx-marker, #sfx tr');
  if(videoClip)return openClipMenu(event,'video',+videoClip.dataset.index);
  if(sub)return openClipMenu(event,'subtitle',+(sub.dataset.index??sub.dataset.i));
  if(sound){const index=sound.matches('.sfx-marker')?+sound.dataset.index:[...$('#sfx').children].indexOf(sound);if(index>=0)openClipMenu(event,'sound',index)}
});
function trimAtPlayhead(side){
  const row=Edit.layout(currentClips())[selectedVideoIndex],at=timelineNow();
  if(!row||at<=row.start||at>=row.end)return status('请把播放头放在片段内部');
  const source=row.source_start+at-row.start;
  trimVideo(selectedVideoIndex,side==='left'?source:row.source_start,side==='right'?source:row.source_end);
}
contextMenu.onclick=event=>{
  const action=event.target.closest('button')?.dataset.action;hideClipMenu();
  if(action==='delete')deleteSelection();else if(action==='split')splitSelection();else if(action==='trimLeft')trimAtPlayhead('left');else if(action==='trimRight')trimAtPlayhead('right');
};
document.addEventListener('pointerdown',e=>{if(!contextMenu.contains(e.target))hideClipMenu()},true);
document.addEventListener('scroll',hideClipMenu,true);window.addEventListener('resize',hideClipMenu);
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){hideClipMenu();return}
  if(!contextMenu.hidden&&['ArrowDown','ArrowUp'].includes(e.key)){
    e.preventDefault();const buttons=[...contextMenu.querySelectorAll('button')],index=buttons.indexOf(document.activeElement);buttons[(index+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length].focus();return;
  }
  if(e.target.closest('input,textarea,select,[contenteditable="true"]'))return;
  const key=e.key.toLowerCase();
  if((e.ctrlKey||e.metaKey)&&key==='z'){e.preventDefault();e.shiftKey?restoreEdit(editRedo,editUndo):restoreEdit(editUndo,editRedo);return}
  if((e.ctrlKey||e.metaKey)&&key==='y'){e.preventDefault();restoreEdit(editRedo,editUndo);return}
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();hideClipMenu();deleteSelection()}
  else if(key==='s'){e.preventDefault();splitSelection()}
  else if(key==='i')trimAtPlayhead('left');else if(key==='o')trimAtPlayhead('right');
});
renderVideoEditor();renderEditHistory();
