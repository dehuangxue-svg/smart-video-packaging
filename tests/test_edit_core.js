const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const Edit=vm.runInNewContext(fs.readFileSync('static/edit-core.js','utf8')+';Edit');
const plain=value=>JSON.parse(JSON.stringify(value));
const project={video_clips:[{id:'a',source_start:10,source_end:20}],subtitles:[
  {start:0,end:2,text:'keep'},{start:3,end:5,text:'remove'},{start:2,end:7,text:'cross'},{start:8,end:10,text:'later'}],
  sound_markers:[{time:1,duration:4},{time:4,duration:.5},{time:8,duration:1}],settings:{hook_end:8},visual:{samples:[{time:4},{time:9}]},asr_quality:{}};
Edit.removeRange(project,3,6);
assert.deepEqual(plain(project.video_clips.map(c=>[c.source_start,c.source_end])),[[10,13],[16,20]]);
assert.equal(Edit.duration(project.video_clips),7);
assert.deepEqual(plain(project.subtitles.map(s=>[s.start,s.end,s.text])),[[0,2,'keep'],[2,4,'cross'],[5,7,'later']]);
assert.equal(project.subtitles[1].edit_review,true);
assert.deepEqual(plain(project.sound_markers.map(m=>[m.time,m.duration])),[[1,2],[5,1]]);
assert.equal(Edit.locate(project.video_clips,3).source,16);
assert.equal(Edit.sourceTime(project.video_clips,1,18),5);
assert.equal(Edit.locate(project.video_clips,7).source,20);
assert.equal(Edit.split(project.video_clips,1,5),true);
assert.equal(Edit.duration(project.video_clips),7);
assert.equal(Edit.split(project.video_clips,1,3),false);
Edit.removeRange(project,0,7);
assert.equal(Edit.duration(project.video_clips),0);assert.equal(Edit.locate(project.video_clips,0),null);
assert.equal(project.subtitles.length,0);assert.equal(project.sound_markers.length,0);
console.log('Edit mappings, ripple captions/sounds, split boundaries and empty timeline passed');
