// Editing uses output-timeline seconds; source ranges are never overwritten.
const Edit = (() => {
  const copy = value => JSON.parse(JSON.stringify(value));
  const duration = clips => clips.reduce((n,c)=>n+c.source_end-c.source_start,0);
  function layout(clips) {
    let at=0;
    return clips.map((clip,index)=>{const start=at;at+=clip.source_end-clip.source_start;return {...clip,index,start,end:at}});
  }
  function locate(clips,time) {
    const rows=layout(clips), end=duration(clips);
    if(!rows.length)return null;
    time=Math.max(0,Math.min(end,time));
    const row=rows.find(c=>time<c.end-0.00001)||rows.at(-1);
    return {...row,source:row.source_start+Math.min(row.end-row.start,time-row.start)};
  }
  function sourceTime(clips,index,time) {
    const row=layout(clips)[index];
    return row?row.start+Math.max(0,Math.min(row.end-row.start,time-row.source_start)):0;
  }
  const remap = (time,start,end) => time<=start?time:time>=end?time-(end-start):start;
  function removeRange(project,start,end,naturalDuration=()=>0.3) {
    const rows=layout(project.video_clips), next=[];
    for(const row of rows){
      if(row.end<=start||row.start>=end){next.push(project.video_clips[row.index]);continue}
      if(row.start<start)next.push({...project.video_clips[row.index],source_end:row.source_start+start-row.start});
      if(row.end>end)next.push({...project.video_clips[row.index],id:row.id+'-r',source_start:row.source_start+end-row.start});
    }
    project.video_clips=next;
    project.subtitles=(project.subtitles||[]).flatMap(sub=>{
      const a=remap(+sub.start,start,end), b=remap(+sub.end,start,end);
      if(b-a<0.03)return [];
      const affected=sub.start<end&&sub.end>start;
      return [{...sub,start:+a.toFixed(6),end:+b.toFixed(6),...(affected?{edit_review:true}:{})}];
    });
    // An effect whose trigger is removed is removed too; later triggers ripple.
    project.sound_markers=(project.sound_markers||[]).flatMap(marker=>{
      const at=+marker.time;
      if(at>=start&&at<end)return [];
      let length=+(marker.duration??naturalDuration(marker.type));
      if(at<start&&at+length>start)length=start-at;
      if(length<0.08)return [];
      return [{...marker,time:+remap(at,start,end).toFixed(6),duration:length}];
    });
    if(project.settings)project.settings.hook_end=remap(+(project.settings.hook_end||8),start,end);
    if(project.visual?.samples)project.visual.samples=project.visual.samples.filter(x=>x.time<start||x.time>=end).map(x=>({...x,time:remap(x.time,start,end)}));
    project.speech_segments=(project.speech_segments||[]).flatMap(x=>{const a=remap(x.start,start,end),b=remap(x.end,start,end);return b>a?[{...x,start:a,end:b}]:[]});
    if(project.asr_quality&&Object.keys(project.asr_quality).length)project.asr_quality.edit_review=true;
  }
  function split(clips,index,time) {
    const row=layout(clips)[index];
    if(!row||time<=row.start+0.025||time>=row.end-0.025)return false;
    const source=row.source_start+time-row.start,clip=clips[index];
    clips.splice(index,1,{...clip,source_end:source},{...clip,id:clip.id+'-s'+Date.now(),source_start:source});return true;
  }
  return {copy,duration,layout,locate,sourceTime,removeRange,split};
})();
