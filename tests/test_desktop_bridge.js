const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/desktop.js'), 'utf8');

(async () => {
  // Opening an ordinary browser tab must not install desktop handlers.
  vm.runInNewContext(source, {window:{}});
  const elements = new Map(), messages = [], storage = new Map();
  const context = vm.createContext({console, setInterval:()=>0,
    window:{chrome:{webview:{postMessage:value=>messages.push(value)}}},
    localStorage:{getItem:key=>storage.get(key)||null, setItem:(key,value)=>storage.set(key,value)},
    document:{addEventListener(){}}, UI:{language:'zh'}, status:()=>{},
    $:selector=>{if(!elements.has(selector))elements.set(selector,{value:'',disabled:false,click(){}});return elements.get(selector);}
  });
  vm.runInContext(`
    var state={video:'', subtitles:[], settings:{}};
    var failSave=false, finishSave=null, delaySave=false;
    function pullSettings() {}
    async function post(url,data) {
      if(url==='/api/save' && failSave) throw Error('test failure');
      if(url==='/api/save' && delaySave) await new Promise(resolve=>finishSave=resolve);
      return {};
    }
    async function load() { await post('/api/load',{}); state={video:'D:/test.mp4',subtitles:[],settings:{}}; }
  `,context);
  vm.runInContext(source, context);
  await vm.runInContext('load()', context);
  assert.equal(context.window.DesktopShell.hasUnsavedChanges(),false);
  assert.equal(storage.get('smartPackaging.desktop.lastVideo'),'D:/test.mp4');
  vm.runInContext("state.subtitles.push({start:0,end:2,text:'test'})",context);
  assert.equal(context.window.DesktopShell.hasUnsavedChanges(),true);
  context.failSave=true;
  assert.equal(await context.window.DesktopShell.saveForClose(),false);
  assert.equal(context.window.DesktopShell.hasUnsavedChanges(),true);
  context.failSave=false;
  assert.equal(await context.window.DesktopShell.saveForClose(),true);
  assert.equal(context.window.DesktopShell.hasUnsavedChanges(),false);
  context.delaySave=true;
  const pending=context.window.DesktopShell.saveForClose();
  vm.runInContext("state.subtitles[0].text='edited while saving'",context);
  context.finishSave(); await pending;
  assert.equal(context.window.DesktopShell.hasUnsavedChanges(),true,'A late save must not mark subsequent edits as saved');
  assert.ok(messages.length>0);
  console.log('Desktop bridge: browser isolation, dirty tracking, save failures and concurrent edits PASS');
})();
