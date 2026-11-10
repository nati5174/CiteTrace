/* Real browser regression checks using Chromium's protocol and Node's built-in WebSocket. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const [target, origin, widthText, output, pythonExecutable] = process.argv.slice(2);
const width = Number(widthText);
const socket = new WebSocket(target);
let nextId = 0;
const pending = new Map();
const errors = [];
let dataMode = 'normal';
let heldRequest;
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const entry = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) entry.reject(Error(JSON.stringify(message.error)));
    else entry.resolve(message.result);
  }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
  if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error')
    errors.push(JSON.stringify(message.params.args));
  if (message.method === 'Fetch.requestPaused') {
    const requestId = message.params.requestId;
    if (dataMode === 'pending') heldRequest = requestId;
    else void send('Fetch.continueRequest', {requestId});
  }
});
function send(method, params = {}) {
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {
    expression, awaitPromise: true, returnByValue: true, userGesture:true
  });
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function until(expression) {
  await evaluate(`(async()=>{for(let i=0;i<200;i++){
    if(${expression})return;await new Promise(r=>setTimeout(r,25));
  }throw Error('Timed out: '+${JSON.stringify(expression)})})()`);
}
async function key(key, code, virtualKey) {
  await send('Input.dispatchKeyEvent', {type:'keyDown', key, code,
    windowsVirtualKeyCode:virtualKey, text:key==='Enter'?'\r':undefined});
  await send('Input.dispatchKeyEvent', {type:'keyUp', key, code, windowsVirtualKeyCode:virtualKey});
}
async function screenshot(name) {
  const image = await send('Page.captureScreenshot', {captureBeyondViewport:false});
  const png=Buffer.from(image.data,'base64');
  assert.equal(png.readUInt32BE(16),width,'screenshot width');
  assert.equal(png.readUInt32BE(20),900,'screenshot height');
  fs.writeFileSync(path.join(output, `${width}-${name}.png`),png);
}
async function layout() {
  return evaluate(`({width:innerWidth,
    overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,
    bodyOverflow:document.body.scrollWidth>document.documentElement.clientWidth,
    nav:[...document.querySelectorAll('.nav nav a')].map(a=>({href:a.hash,
      visible:a.getClientRects().length>0, label:a.textContent.trim()}))})`);
}
async function assertContrast() {
  const failures = await evaluate(`(()=>{
    function luminance(rgb){return rgb.slice(0,3).map(x=>x/255)
      .map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4)
      .reduce((sum,x,i)=>sum+x*[.2126,.7152,.0722][i],0)}
    const failures=[];
    for(const e of document.querySelectorAll('body *')){
      if(!e.getClientRects().length||!Array.from(e.childNodes).some(n=>n.nodeType===3&&/[a-zA-Z0-9]/.test(n.textContent)))continue;
      const s=getComputedStyle(e);if(s.visibility==='hidden')continue;
      let parent=e,bg;while(parent){bg=getComputedStyle(parent).backgroundColor;
        if(bg!=='rgba(0, 0, 0, 0)')break;parent=parent.parentElement}
      const fg=luminance(s.color.match(/[\\d.]+/g).map(Number));
      const back=luminance((parent?bg:'rgb(255,255,255)').match(/[\\d.]+/g).map(Number));
      const ratio=(Math.max(fg,back)+.05)/(Math.min(fg,back)+.05);
      if(ratio<4.5)failures.push({tag:e.tagName,class:e.className,text:e.textContent.slice(0,50),ratio});
    }return failures})()`);
  assert.deepEqual(failures, [], `text contrast: ${JSON.stringify(failures)}`);
}
(async () => {
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve);socket.addEventListener('error', reject);
  });
  await send('Page.enable');await send('Runtime.enable');await send('Accessibility.enable');
  await send('Emulation.setDeviceMetricsOverride', {width,height:900,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:origin});
  await until("document.querySelectorAll('.paper-link').length===8");
  await evaluate('document.fonts.ready');
  assert.equal((await layout()).overflow,false);
  assert.equal(await evaluate("document.fonts.check('16px Plex') && document.fonts.check('16px PlexMono')"),true);
  const frozen=JSON.parse(fs.readFileSync('public-demo/data.json','utf8'));
  const atlasPages=[];
  for(let pair=0;pair<(width<=800?4:1);pair++){
    atlasPages.push(await evaluate(`({sources:[...document.querySelectorAll('.map-source')].map(a=>a.dataset.sourceId),
      searches:[...document.querySelectorAll('.map-result')].map(a=>({id:a.dataset.sourceId,provider:a.dataset.provider,
        ranks:[...a.querySelectorAll('.rank-cell')].map(x=>Number(x.textContent)),label:a.getAttribute('aria-label'),href:a.hash}))})`));
    if(width<=800&&pair<3){
      await evaluate("document.querySelector('.atlas-controls button:last-child').focus()");
      await key('Enter','Enter',13);
    }
  }
  const atlasSources=atlasPages.flatMap(page=>page.sources);
  const atlasSearches=atlasPages.flatMap(page=>page.searches);
  assert.deepEqual(atlasSources,frozen.papers.map(p=>p.id),'Atlas reaches all frozen sources');
  assert.equal(atlasSearches.length,16,'Atlas reaches all provider searches');
  for(const item of atlasSearches){
    const paper=frozen.papers.find(p=>p.id===item.id);
    const expected=paper.results[item.provider].candidates.map(c=>c.rank);
    assert.deepEqual(item.ranks,expected,`${item.id} ${item.provider} original ranks`);
    assert.equal(item.href,`#paper=${item.id}&provider=${item.provider}`);
    assert.match(item.label,/undetermined|No candidates to assess/);
  }
  if(width<=800) await evaluate("document.querySelector('.atlas-controls button:nth-of-type(1)').click();document.querySelector('.atlas-controls button:nth-of-type(1)').click();document.querySelector('.atlas-controls button:nth-of-type(1)').click()");
  await evaluate("document.querySelector('.map-source').focus()");
  await key('Enter','Enter',13);await until("document.querySelectorAll('.candidate-record').length===5");
  assert.equal(await evaluate("location.hash"),'#paper=2611.07721');
  await evaluate('history.back()');await until("!document.querySelector('#overview').hidden");
  await evaluate("document.querySelector('#main').scrollIntoView()");
  await assertContrast();await screenshot('home');
  await key('Tab','Tab',9);
  await evaluate("document.querySelector('.mast a').focus()");
  assert.equal(await evaluate("document.activeElement.matches(':focus-visible')"),true);
  assert.equal(await evaluate("getComputedStyle(document.activeElement).outlineColor"),
    'rgb(199, 216, 233)', 'light focus indicator on graphite');
  const rows=await evaluate("[...document.querySelectorAll('#matrix tr')].map(r=>[...r.children].map(c=>c.textContent))");
  assert.deepEqual(rows,[
    ['OpenAlex','1 / 8','1','All returned identities undetermined','0–1 / 8','1 anonymous; 7 API key'],
    ['Crossref','8 / 8','40','All returned identities undetermined','0–8 / 8','8 anonymous']]);
  const ax=await send('Accessibility.getFullAXTree');
  const sourceLinks=ax.nodes.filter(n=>n.role?.value==='link'&&n.name?.value.startsWith('Inspect ')
    &&n.name.value.includes('OpenAlex:')&&n.name.value.includes('Crossref:'));
  assert.equal(sourceLinks.length,8,'provider association at every viewport');
  assert.equal(ax.nodes.filter(n=>n.role?.value==='rowheader').length,2,'matrix row semantics');
  await evaluate("document.querySelector('#findings').scrollIntoView()");await screenshot('findings');
  const downloadDir=path.resolve(output,`downloads-${width}`);fs.mkdirSync(downloadDir,{recursive:true});
  await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloadDir});
  for(const filename of ['data.json','experiment-manifest.json','verify.py']){
    await evaluate(`document.querySelector('.artifact-links a[href="${filename}"]').click()`);
    const destination=path.join(downloadDir,filename);
    for(let i=0;!fs.existsSync(destination)&&i<200;i++)await new Promise(r=>setTimeout(r,25));
    assert.deepEqual(fs.readFileSync(destination),fs.readFileSync(path.join('public-demo',filename)));
  }
  const verified=spawnSync(pythonExecutable,['-I',path.join(downloadDir,'verify.py'),
    path.join(downloadDir,'data.json'),path.join(downloadDir,'experiment-manifest.json')],{encoding:'utf8'});
  assert.equal(verified.status,0,verified.stdout+verified.stderr);
  assert.equal(JSON.parse(verified.stdout).candidate_entries,41);
  // Cohort changes do not alter either provider's matrix denominator.
  await evaluate("const select=document.querySelector('#cohort');select.value='1-7';select.dispatchEvent(new Event('change'))");
  assert.equal(await evaluate("document.querySelectorAll('.paper-link').length"),2);
  await evaluate("document.querySelector('#cohort').value='all';document.querySelector('#cohort').dispatchEvent(new Event('change'))");
  await evaluate("document.querySelector('#explore').scrollIntoView();document.querySelector('.paper-link').focus()");
  await screenshot('papers');await key('Enter','Enter',13);
  await until("document.querySelectorAll('.candidate-record').length===5");
  assert.equal(await evaluate("document.activeElement.id"),'inspection-title');
  assert.equal(await evaluate("document.querySelector('.provider-nav [aria-pressed=true]').textContent"),'Crossref · 5 candidates');
  assert.equal(await evaluate("document.querySelectorAll('.evidence-path .path-stages li').length"),4);
  assert.match(await evaluate("document.querySelector('.evidence-path').textContent"),/Source paper.*Provider search.*Ranked candidates.*Identity evidence/s);
  assert.equal(await evaluate("document.querySelectorAll('.rank-jumps button').length"),5);
  await evaluate("document.querySelector('.rank-jumps button[aria-label=\"Jump to provider rank 5\"]').click()");
  assert.equal(await evaluate("Number(document.activeElement.closest('.candidate-record').querySelector('.rank').textContent)"),5);
  await assertContrast();await screenshot('inspection');
  assert.equal(await evaluate("document.querySelector('.candidate-record h3').getBoundingClientRect().top<innerHeight"),true,'first candidate visible');
  // Tab / Enter actuates the first provider button after the focused heading and source links.
  await evaluate("document.querySelector('.provider-nav button').focus()");await key('Enter','Enter',13);
  assert.equal(await evaluate("document.querySelectorAll('.candidate-record').length"),0);
  assert.match(await evaluate("document.querySelector('.workbench').textContent"),/does not establish absence/);
  await evaluate("document.querySelector('.provider-nav button:last-child').click()");
  assert.equal(await evaluate("document.activeElement.getAttribute('aria-pressed')"),'true');
  await evaluate('history.back()');await until("!document.querySelector('#overview').hidden");
  assert.equal(await evaluate("document.activeElement.className"),'paper-link');
  await evaluate('history.forward()');await until("document.querySelectorAll('.candidate-record').length===5");
  // Real direct-entry links, not calls into renderer internals, exercise every recorded search.
  const data=JSON.parse(fs.readFileSync('public-demo/data.json','utf8'));
  let candidateCount=0;
  for(const paper of data.papers){
    for(const provider of ['openalex','crossref']){
      await send('Page.navigate',{url:origin+`/#paper=${paper.id}&provider=${provider}`});
      await until("document.querySelector('#inspection-title')");
      const ranks=await evaluate("[...document.querySelectorAll('.rank')].map(n=>Number(n.textContent))");
      assert.deepEqual(ranks,paper.results[provider].candidates.map(c=>c.rank));candidateCount+=ranks.length;
      assert.equal((await layout()).overflow,false);
    }
  }
  assert.equal(candidateCount,41);
  await send('Page.navigate',{url:origin+'/#paper=2611.07721'});
  await until("document.querySelectorAll('.candidate-record').length===5");
  await evaluate("document.documentElement.style.fontSize='200%'");
  assert.equal((await layout()).overflow,false);await screenshot('inspection-text-200');
  await send('Page.navigate',{url:origin+'/methodology.html'});await until("document.querySelector('.method-page')");
  await evaluate('document.fonts.ready');await assertContrast();await screenshot('methodology');
  await evaluate("document.documentElement.style.fontSize='200%'");assert.equal((await layout()).overflow,false,
    JSON.stringify(await evaluate("({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,elements:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>document.documentElement.clientWidth).map(e=>({tag:e.tagName,class:e.className,right:e.getBoundingClientRect().right,text:e.textContent.slice(0,60)}))})")));
  await screenshot('methodology-text-200');
  // Invalid direct link provides a route back to the unchanged inventory.
  await send('Page.navigate',{url:origin+'/#paper=unknown'});await until("document.querySelector('#inspection h1')");
  assert.match(await evaluate("document.querySelector('#inspection').textContent"),/Source paper not found/);
  await evaluate("document.querySelector('#inspection a').click()");await until("!document.querySelector('#overview').hidden");
  // Delay then fail data; no half-rendered evidence may remain visible.
  await send('Fetch.enable',{patterns:[{urlPattern:'*data.json',requestStage:'Request'}]});dataMode='pending';
  await send('Page.navigate',{url:origin});await until("document.querySelector('#loading')");
  for(let i=0;i<200&&!heldRequest;i++)await new Promise(r=>setTimeout(r,25));
  assert.ok(heldRequest);assert.equal(await evaluate("document.querySelector('#overview').hidden"),true);
  await send('Fetch.fulfillRequest',{requestId:heldRequest,responseCode:404,body:''});
  await until("document.querySelector('#loading').getAttribute('role')==='alert'");
  assert.equal(await evaluate("document.querySelector('#overview').hidden"),true);
  assert.match(await evaluate("document.querySelector('#loading').textContent"),/Refresh to try again/);
  await assertContrast();await screenshot('error');await send('Fetch.disable');dataMode='normal';
  await send('Page.navigate',{url:origin});await until("document.querySelectorAll('.paper-link').length===8");
  await evaluate("document.querySelector('.skip').focus()");await key('Enter','Enter',13);
  assert.equal(await evaluate('document.activeElement.tagName'),'MAIN');
  await evaluate("document.documentElement.style.fontSize='200%'");
  assert.equal((await layout()).overflow,false,
    JSON.stringify(await evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth).map(e=>({tag:e.tagName,class:e.className,text:e.textContent.slice(0,60)}))")));
  await screenshot('home-text-200');
  assert.deepEqual(errors,[]);
  const report={width,height:900,papers:8,candidates:candidateCount,errors,
    offlineVerifier:'PASS',keyboard:'PASS',textScaling200:'PASS',history:'PASS',accessibleProviders:'PASS'};
  fs.writeFileSync(path.join(output,`${width}-report.json`),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));socket.close();
})().catch(error=>{console.error(error);socket.close();process.exitCode=1});
