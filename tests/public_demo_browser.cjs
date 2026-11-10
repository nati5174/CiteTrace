/* Real browser regression checks using Chromium's protocol and Node's built-in WebSocket. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const [target, origin, widthText, output] = process.argv.slice(2);
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
  const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
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
  fs.writeFileSync(path.join(output, `${width}-${name}.png`), Buffer.from(image.data, 'base64'));
}
async function layout() {
  return evaluate(`({width:innerWidth, overflow:document.documentElement.scrollWidth>innerWidth,
    bodyOverflow:document.body.scrollWidth>innerWidth,
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
  await new Promise((resolve, reject) => {socket.addEventListener('open', resolve);socket.addEventListener('error', reject);});
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await send('Emulation.setDeviceMetricsOverride', {width, height:900, deviceScaleFactor:1, mobile:false});
  await send('Page.navigate', {url:origin});
  await until("document.querySelectorAll('.paper-row').length===8");
  let state = await layout();
  assert.equal(state.width, width);
  assert.equal(state.overflow, false, 'page horizontal overflow');
  assert.equal(state.bodyOverflow, false, 'body horizontal overflow');
  assert.deepEqual(state.nav.map(a=>[a.href,a.visible]), [['#findings',true],['#explore',true],['#methodology',true]]);
  assert.equal(await evaluate("document.querySelector('.nav nav').getAttribute('aria-label')"), 'Main navigation');
  assert.equal(await evaluate(`[...document.querySelectorAll('.paper-meta,.status,.status small,.tabs button,.candidate-label')]
    .every(e=>parseFloat(getComputedStyle(e).fontSize)>=12)`),true,'research label font size');
  await assertContrast();
  await screenshot('home');
  // Actual Tab and Enter events, not click() substitutes, exercise native link behavior.
  let previous = '.nav .brand';
  for(const id of ['findings','explore','methodology']){
    await evaluate(`document.querySelector(${JSON.stringify(previous)}).focus()`);
    await key('Tab','Tab',9);
    assert.equal(await evaluate("document.activeElement.hash"), '#'+id);
    assert.equal(await evaluate("document.activeElement.matches(':focus-visible')"), true);
    assert.notEqual(await evaluate("getComputedStyle(document.activeElement).outlineStyle"), 'none');
    await key('Enter','Enter',13);
    assert.equal(await evaluate('location.hash'), '#'+id);
    previous = `.nav nav a[href="#${id}"]`;
  }
  await evaluate("document.querySelector('#explore').scrollIntoView({behavior:'instant'})");
  await screenshot('papers');
  const detailCounts = await evaluate(`(()=>{
    const rows=[...document.querySelectorAll('.paper-row')];const counts=[];
    for(const row of rows){row.click();const d=document.querySelector('#detail');
      if(!d.open||d.scrollWidth>d.clientWidth)throw Error('dialog overflow or not open');
      counts.push(document.querySelectorAll('#detail-content .candidate-label').length);
      document.querySelector('#close-detail').click();if(d.open)throw Error('dialog did not close');
    }return counts})()`);
  assert.deepEqual(detailCounts,[5,5,5,5,5,5,6,5]);
  await evaluate("document.querySelector('[data-cohort=all]').click()");
  const candidateMetadataMatches = await evaluate(`(async()=>{
    const data=await(await fetch('data.json')).json();
    const rows=[...document.querySelectorAll('.paper-row')];
    return rows.every((row,i)=>{
      row.click();const items=[...document.querySelectorAll('#detail-content .candidate-label')];
      const expected=['openalex','crossref'].flatMap(p=>data.papers[i].results[p].candidates);
      const matches=expected.every((c,j)=>{
        const text=items[j].parentElement.textContent;
        return text.includes('RANK '+c.rank)&&text.includes(c.judgment)&&text.includes(c.reason)&&
          text.includes(c.title||'Title unavailable');
      });document.querySelector('#close-detail').click();return matches;
    });})()`);
  assert.equal(candidateMetadataMatches,true,'rankings and identity judgments');
  await evaluate("document.querySelector('.paper-row').focus()");
  assert.equal(await evaluate("document.activeElement.matches('.paper-row')"), true, 'paper focus');
  await key('Enter','Enter',13);
  await until("document.querySelector('#detail').open");
  await assertContrast();
  await screenshot('dialog');
  await key('Escape','Escape',27);
  await until("!document.querySelector('#detail').open");
  assert.equal(await evaluate("document.activeElement.matches('.paper-row')"), true);
  const filters = await evaluate(`(()=>{
    const counts=[];for(const b of document.querySelectorAll('[data-cohort]')){
      b.click();counts.push(document.querySelectorAll('.paper-row').length);
      if(b.getAttribute('aria-pressed')!=='true')throw Error('filter state');
      if(document.documentElement.scrollWidth>innerWidth)throw Error('filter overflow');
    }return counts})()`);
  assert.deepEqual(filters,[8,2,2,2,2]);
  await send('Page.navigate',{url:origin+'/methodology.html'});
  await until("document.querySelectorAll('.principles article').length===5");
  assert.equal((await layout()).overflow,false,'methodology overflow');
  await assertContrast();
  await screenshot('methodology');
  // Delay the real HTTP request, then turn it into an HTTP error.
  dataMode='pending';
  await send('Fetch.enable',{patterns:[{urlPattern:'*/data.json',requestStage:'Request'}]});
  await send('Page.navigate',{url:origin});
  await until("document.querySelector('[data-cohort]')&&typeof drawPapers==='function'");
  await evaluate("document.querySelector('[data-cohort=\"1-7\"]').click();document.querySelector('[data-cohort=all]').click()");
  assert.equal(await evaluate("document.querySelector('#paper-count').textContent"),'LOADING');
  for(let i=0;!heldRequest&&i<100;i++)await new Promise(r=>setTimeout(r,25));
  assert.ok(heldRequest,'data request was intercepted');
  await send('Fetch.fulfillRequest',{requestId:heldRequest,responseCode:404,body:Buffer.from('unavailable').toString('base64')});
  await until("document.querySelector('#paper-count').textContent==='DATA UNAVAILABLE'");
  await evaluate("document.querySelector('[data-cohort=\"1-7\"]').click();document.querySelector('[data-cohort=all]').click()");
  assert.match(await evaluate("document.querySelector('#papers').textContent"),/could not be loaded/);
  assert.match(await evaluate("document.querySelector('#comparison').textContent"),/could not be loaded/);
  assert.equal(await evaluate("document.querySelector('#paper-count').textContent"),'DATA UNAVAILABLE');
  assert.equal((await layout()).overflow,false,'error state overflow');
  await assertContrast();
  dataMode='normal';heldRequest=undefined;
  await send('Fetch.disable');
  assert.deepEqual(errors,[],'JavaScript console/runtime errors');
  console.log(JSON.stringify({width,papers:8,candidates:detailCounts.reduce((a,b)=>a+b,0),errors}));
  socket.close();
})().catch(error=>{console.error(error);socket.close();process.exitCode=1;});
