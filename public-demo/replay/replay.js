'use strict';
(() => {
 const $=id=>document.getElementById(id),{el}=window.CiteProbeUI,camera=window.CiteProbeCamera,reduced=matchMedia('(prefers-reduced-motion:reduce)');
 const phases=['Intended source','Recorded query','Retrieval response','Ranked candidates','Identity comparison','Evidence verdict'];
 const caseLabels=['Hidden Cartographer / proteins','Preprint / EMNLP publication','Language models / voltage control'];
 let data,scenario,selected,time=0,playing=false,lastTime=0,animation=0,resizeFrame=0,phase=0,inspector,layoutMetrics={width:0},playUntil=27;
 const paperNodes=new Map(),paths=[],caseSelections=new Map();
 function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
 async function loadJSON(){const response=await fetch('./data.json',{signal:AbortSignal.timeout(12000)});if(!response.ok)throw Error('The recorded data could not be loaded.');return response.json();}
 function svgPath(className){const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.classList.add('flow-path');if(className)path.classList.add(className);path.setAttribute('pathLength','1');return path;}
 function place(element,position,opacity=1){element.style.width=(position.contentWidth??position.width)+'px';element.style.height=(position.contentHeight??position.height)+'px';element.style.transform=`translate3d(${position.x}px,${position.y}px,0) scale(${position.scale??1})`;element.style.opacity=String(opacity);}
 function titleForPhase(){
  if(phase===0)return 'Start with the intended paper.';
  if(phase===1)return 'Replay the recorded Crossref query.';
  if(phase===2)return 'Returned records are not verified matches.';
  if(phase===3)return 'Five candidates. Original ranks. Select one.';
  if(phase===4)return 'Compare the source and selected candidate.';
  return 'DOI registration does not establish identity.';
 }
 function narrative(){
  if(phase===4&&reduced.matches)return 'Recorded evidence and verifier outputs. Inspect the trace.';
  if($('viewport').clientWidth<500){
   if(phase===0)return 'Recorded source metadata.';
   if(phase===1)return 'Recorded metadata query; no LLM generation.';
   if(phase===2)return `${scenario.candidates.length} recorded Crossref results.`;
   if(phase===3)return `Scroll through the recorded ranks; select a candidate.`;
   if(phase===4)return time<17.5?'Compare recorded titles.':time<18.8?'Compare identifiers.':'Recorded evidence and verifier outputs.';
   return `Engine C: ${selected.outputs.C.verdict} · provisional result.`;
  }
  if(phase===0)return 'Recorded source metadata.';
  if(phase===1)return 'Recorded metadata query; no LLM generation.';
  if(phase===2)return `${scenario.candidates.length} recorded Crossref results; no live request.`;
  if(phase===3)return `Rank ${selected.rank} of ${scenario.candidates.length}; retrieval order, not identity.`;
  if(phase===4)return time<17.5?'Different titles alone do not establish a mismatch.':time<18.8?'Different identifiers can refer to versions of one work.':'Solid links show evidence in C’s recorded trace.';
  return selected.outputs.C.verdict==='ABSTAIN'?'Insufficient evidence. The earlier audit is a separate assessment.':selected.outputs.C.verdict==='CORRECT'?'Same work; different document versions.':'The evidence rule provisionally identifies a different work.';
 }
 function paper(candidate){
  const button=el('button',undefined,'document candidate-document'),top=el('span',undefined,'paper-heading');
  button.id='paper-'+candidate.rank;button.type='button';button.dataset.rank=candidate.rank;button.dataset.caseId=candidate.case_id;button.setAttribute('aria-label',`Crossref rank ${candidate.rank}: ${candidate.candidate.title}. Select for investigation.`);
  top.append(el('span',`Rank ${candidate.rank} · Crossref`),el('span','Selected','selection-label'));
  button.append(el('div',undefined,'fold'),top,el('strong',candidate.candidate.title,'doc-title'),el('span',candidate.candidate.doi,'doc-id mono'),el('span',candidate.candidate.authors.join('; '),'doc-authors'));
  button.querySelector('.fold').setAttribute('aria-hidden','true');
  button.title=`Rank ${candidate.rank}: ${candidate.candidate.title}\nDOI: ${candidate.candidate.doi}`;
  button.addEventListener('click',()=>chooseCandidate(candidate.case_id,true));return button;
 }
 function mount(){
  paperNodes.clear();$('candidate-documents').replaceChildren();paths.length=0;$('connection-paths').replaceChildren();
  const queryPath=svgPath('query-line');paths.push(queryPath);$('connection-paths').append(queryPath);
  scenario.candidates.forEach(candidate=>{const element=paper(candidate);paperNodes.set(candidate.rank,element);$('candidate-documents').append(element);const path=svgPath();paths.push(path);$('connection-paths').append(path);});
  const comparisonPath=svgPath();comparisonPath.id='comparison-path';paths.push(comparisonPath);$('connection-paths').append(comparisonPath);
  for(const side of ['source','candidate']){const p=svgPath('evidence-link');p.id=side+'-evidence-link';$('connection-paths').append(p);}
  const packet=document.createElementNS('http://www.w3.org/2000/svg','circle');packet.id='query-packet';packet.setAttribute('r','8');packet.setAttribute('fill','var(--cp-accent)');packet.setAttribute('stroke','white');packet.setAttribute('stroke-width','3');$('connection-paths').append(packet);
  $('source-title').textContent=scenario.source.title;$('source-id').textContent='arXiv:'+scenario.source.arxiv_id;$('source-authors').textContent=scenario.source.authors.join('; ');
  $('source-meta').textContent=`${scenario.source.authors.length} authors · ${scenario.source.year}`;$('provider-meta').textContent=`HTTP ${scenario.search.http_status} · ${scenario.candidates.length} records`;
  const recordedQuery=scenario.search.parameters['query.bibliographic'];$('query-token').querySelector('small').textContent=recordedQuery;$('query-token').title=recordedQuery;
  updateCandidate();
 }
 function evidenceFor(side){
  const records=selected.evidence.filter(e=>e.side===side);
  return records.find(e=>e.kind==='FULL_TEXT')||records.find(e=>e.kind==='ABSTRACT')||records[0];
 }
 function evidenceNote(id,evidence){
  const block=$(id);block.replaceChildren();block.classList.toggle('indexed',evidence?.origin==='INDEXED');
  if(!evidence)return;
  const kind={REGISTRATION:'DOI registration',ABSTRACT:'Abstract',FULL_TEXT:'Main text',RELATIONSHIP:'Identifier relation'}[evidence.kind];
  block.append(el('strong',kind),el('span',evidence.origin==='INDEXED'?'Indexed · excluded as primary':selected.outputs.C.used_evidence_ids.includes(evidence.evidence_id)?'In verifier C’s recorded trace':'Available; not in C’s trace'));
 }
 function updateCandidate(){
  layoutMetrics.width=0;
  for(const candidate of scenario.candidates){const element=paperNodes.get(candidate.rank),active=candidate.case_id===selected.case_id;element.classList.toggle('selected',active);element.setAttribute('aria-pressed',String(active));element.querySelector('.selection-label').hidden=!active;}
  const buttons=scenario.candidates.map(candidate=>{const b=el('button',String(candidate.rank));b.type='button';b.setAttribute('aria-label',`Select recorded candidate rank ${candidate.rank}`);b.setAttribute('aria-pressed',String(candidate.case_id===selected.case_id));b.addEventListener('click',()=>{chooseCandidate(candidate.case_id);$('rank-picker').querySelector(`[aria-label="Select recorded candidate rank ${candidate.rank}"]`)?.focus({preventScroll:true});});return b;});
  $('rank-picker').replaceChildren(el('span','Recorded ranks'),...buttons);
  const checks=[],verdictChecks=[];
  for(const a of ['A','B','C']){
   const output=selected.outputs[a],name=a==='A'?'DOI exists?':a==='B'?'Metadata identity':'Evidence identity';
   const check=el('div',undefined,'check');check.dataset.approach=a;check.append(el('h3',a+' · '+name),el('strong',a==='A'?output.doi_existence:output.verdict),el('span',a==='A'?'Identity: ABSTAIN':'Provisional output'));checks.push(check);
   const small=el('div');small.append(el('span',a+' · '+(a==='A'?'identity':a==='B'?'metadata':'evidence')),el('strong',output.verdict));verdictChecks.push(small);
  }
  $('checks').replaceChildren(...checks);$('verdict-checks').replaceChildren(...verdictChecks);
  $('registration-result').textContent=selected.outputs.A.doi_existence==='EXISTS'?'DOI REGISTERED':`DOI ${selected.outputs.A.doi_existence}`;
  $('verdict-title').textContent=selected.outputs.C.verdict;$('verdict').dataset.verdict=selected.outputs.C.verdict;
  $('verdict-summary').textContent=selected.outputs.C.verdict==='CORRECT'?'Same intellectual work':selected.outputs.C.verdict==='INCORRECT'?'Different scientific work':'Identity not established';
  $('verdict-explanation').textContent=selected.outputs.C.verdict==='CORRECT'?'Main text and authors support the same work across different versions.':selected.outputs.C.verdict==='INCORRECT'?'Primary abstracts describe different research, with different authors.':'The DOI exists, but the available evidence does not establish paper identity.';
  $('audit-reference').textContent=`Earlier machine-assisted audit: ${selected.audit_label}. Separate assessment; human adjudication pending.`;
  evidenceNote('source-evidence',evidenceFor('SOURCE'));evidenceNote('candidate-evidence',evidenceFor('CANDIDATE'));
 }
 function visible(position,g,w,h){
  const x=g.camera.tx+position.x*g.camera.scale,y=g.camera.ty+position.y*g.camera.scale;
  return x+position.width*g.camera.scale>4&&x<w-4&&y+position.height*g.camera.scale>4&&y<h-4;
 }
 function contained(position,g){
  const a=g.safeArea,s=g.camera.scale,x=g.camera.tx+position.x*s,y=g.camera.ty+position.y*s;
  return x>=a.x-1&&y>=a.y-1&&x+position.width*s<=a.x+a.width+1&&y+position.height*s<=a.y+a.height+1;
 }
 function candidateHeight(width,rank=selected.rank){
  const clone=paperNodes.get(rank).cloneNode(true);clone.removeAttribute('id');clone.hidden=false;
  clone.style.cssText=`position:absolute;visibility:hidden;pointer-events:none;width:${width}px;height:auto;transform:none;`;
  $('world').append(clone);const height=clone.offsetHeight;clone.remove();return height;
 }
 function render(){
  if(!selected)return;
  const intendedPhase=camera.phaseAt(time),verdict=$('verdict');verdict.hidden=intendedPhase!==5;
  const viewport=$('viewport'),w=viewport.clientWidth;if(!w)return;document.querySelector('.app').dataset.compact=String(w<640);
  phase=intendedPhase;$('phase-select').value=String(phase);$('story-caption').textContent=titleForPhase();$('narrative').textContent=narrative();
  $('source-context').textContent=w<500?`${scenario.source.arxiv_id} / rank ${selected.rank}`:`arXiv:${scenario.source.arxiv_id} · Crossref rank ${selected.rank}`;
  if(viewport.scrollLeft||viewport.scrollTop){viewport.scrollLeft=0;viewport.scrollTop=0;}
  $('world').dataset.narrow=String(w<900);
  if(layoutMetrics.width!==w){
   $('checks').hidden=false;$('rank-picker').hidden=false;
   document.querySelectorAll('#checks strong,#checks span').forEach(e=>{e.hidden=false;});
   layoutMetrics={width:w,checksHeight:$('checks').offsetHeight+24,ranksHeight:$('rank-picker').offsetHeight+24};
   if(matchMedia('(max-width:300px)').matches){layoutMetrics.candidateHeights=Object.fromEntries(scenario.candidates.map(c=>[c.rank,candidateHeight(Math.min(390,w-36),c.rank)]));layoutMetrics.candidateHeight=layoutMetrics.candidateHeights[selected.rank];layoutMetrics.comparisonHeight=candidateHeight(w-32);}
  }
  const preliminary=camera.frame(time,w,viewport.clientHeight,selected.rank,reduced.matches,layoutMetrics);
  const sceneHeight=intendedPhase===5?Math.max(420,Math.ceil(verdict.offsetHeight)+40):Math.ceil(preliminary.minimumHeight);
  $('stage-view').style.setProperty('--scene-min-height',sceneHeight+'px');
  const h=viewport.clientHeight;if(!h)return;
  const g=camera.frame(time,w,h,selected.rank,reduced.matches,layoutMetrics);phase=g.phase;
  for(const [name,value] of Object.entries(g.worldSize)){const px=value+'px';if($('world').style[name]!==px){$('world').style[name]=px;$('connections').style[name]=px;}}
  viewport.dataset.active=g.active.join(' ');viewport.dataset.phase=String(phase);viewport.dataset.narrow=String(g.narrow);
  $('world').style.transform=`translate3d(${g.camera.tx}px,${g.camera.ty}px,0) scale(${g.camera.scale})`;
  $('world').dataset.compare=String(phase>=4);$('world').dataset.transition=String(g.comparison>0&&phase<4);$('world').dataset.narrow=String(g.narrow);$('world').dataset.compactSource=String(g.compactSource);$('world').dataset.compactCandidates=String(g.compactCandidates);$('world').style.setProperty('--handoff',String(g.comparison));$('world').inert=phase===5;
  $('source-title').style.fontSize=g.sourceFont+'px';
  $('world').dataset.review=selected.outputs.B.findings.some(f=>f.code==='METADATA_COMPARISON')?g.reviewField:'';
  $('source-context').dataset.review=$('world').dataset.review;
  $('source-document').querySelector('.paper-heading span').textContent=g.narrow?(phase>=4?'Intended source':`Source · ${scenario.source.year}`):'Intended source';
  const backdrop=phase===5?.14:1;
  place($('source-document'),g.source,backdrop);place($('provider'),g.provider,backdrop*g.providerOpacity);
  $('provider').dataset.replaying=String(g.queryProgress>=1&&phase<4);$('provider').querySelector('span:first-child').textContent=g.queryProgress>=1?'Recorded response':'Retrieval provider';
  $('source-document').style.visibility=contained(g.source,g)?'visible':'hidden';$('provider').style.visibility=contained(g.provider,g)?'visible':'hidden';
  $('source-document').setAttribute('aria-hidden',String(!visible(g.source,g,w,h)||phase===5));$('provider').setAttribute('aria-hidden',String(!visible(g.provider,g,w,h)||phase===5));
  g.cards.forEach(card=>{const element=paperNodes.get(card.rank);element.querySelector('.paper-heading>span:first-child').textContent=g.narrow&&phase>=4?`Rank ${card.rank}`:`Rank ${card.rank} · Crossref`;place(element,card,card.opacity*backdrop);element.style.zIndex=String(card.zIndex);element.hidden=card.opacity<.01||!contained(card,g);const available=!element.hidden&&card.opacity>.95&&phase!==5;element.tabIndex=available?0:-1;element.setAttribute('aria-hidden',String(!available));element.inert=!available;
   const path=paths[card.rank];path.setAttribute('d',camera.path(card.path));path.classList.toggle('active-connection',card.selected);path.style.strokeDasharray='1';path.style.strokeDashoffset=String(1-card.reveal);path.style.opacity=String(element.hidden?0:(card.selected?1:.48)*card.opacity*g.providerOpacity*(1-g.comparison)*backdrop);
  });
  paths[0].setAttribute('d',camera.path(g.queryPath));paths[0].style.opacity=String(g.providerOpacity*(1-g.comparison));paths[0].style.strokeDasharray='1';paths[0].style.strokeDashoffset=String(1-g.queryDraw);
  $('query-token').hidden=!g.queryVisible;place($('query-token'),g.queryLabel,g.queryOpacity);
  $('query-packet').setAttribute('cx',String(g.query.x));$('query-packet').setAttribute('cy',String(g.query.y));$('query-packet').style.opacity=String(g.packetOpacity);
  for(const [id,position,opacity] of [['source-evidence',g.sourceEvidence,g.evidenceOpacity],['candidate-evidence',g.candidateEvidence,g.candidateEvidenceOpacity]]){const e=$(id);place(e,position,opacity*backdrop);e.hidden=phase<4||!g.showEvidence;e.setAttribute('aria-hidden',String(phase!==4||!g.showEvidence));const side=id.startsWith('source')?'SOURCE':'CANDIDATE',ev=evidenceFor(side),p=$(id+'-link'),used=ev&&selected.outputs.C.used_evidence_ids.includes(ev.evidence_id);p.style.opacity=String(used&&g.showEvidence?opacity:0);p.setAttribute('d',`M${position.x+position.width/2},${position.y} L${position.x+position.width/2},${position.y-16}`);}
  const compare=$('comparison-path'),candidate=g.cards[selected.rank-1];compare.style.display=g.comparison<=0?'none':'';compare.style.opacity=String(g.comparison*(phase===5?.1:1));
  const a=g.narrow?{x:g.source.x+g.source.width/2,y:g.source.y+g.source.height}:{x:g.source.x+g.source.width,y:g.source.y+g.source.height/2},b=g.narrow?{x:candidate.x+candidate.width/2,y:candidate.y}:{x:candidate.x,y:candidate.y+candidate.height/2};
  compare.setAttribute('d',g.narrow?`M${a.x},${a.y} L${b.x},${b.y}`:`M${a.x},${a.y} C${(a.x+b.x)/2},${a.y} ${(a.x+b.x)/2},${b.y} ${b.x},${b.y}`);
  $('comparison-label').hidden=true;
  $('rank-picker').hidden=phase!==3;$('checks').hidden=!g.checksVisible;$('verdict').hidden=!g.verdictVisible;
  document.querySelectorAll('#checks .check').forEach((check,index)=>{const ready=time>=[16.2,18,20][index]||reduced.matches;check.querySelector('strong').hidden=!ready;check.querySelector('span').hidden=!ready;});
  $('source-context').setAttribute('aria-label',`Intended source arXiv ${scenario.source.arxiv_id}, Crossref rank ${selected.rank}`);
  $('timeline').value=String(time);$('timeline').setAttribute('aria-valuetext',`${time.toFixed(1)} seconds, ${phases[phase]}`);$('time').textContent=String(Math.floor(time)).padStart(2,'0')+' / 27s';
  $('play-toggle').textContent=playing?'Pause':'Play';$('play-toggle').setAttribute('aria-pressed',String(playing));$('previous').disabled=phase===0;$('next').disabled=phase===5;
  $('verdict').style.setProperty('--verdict-reveal',String(reduced.matches?1:Math.min(1,Math.max(0,(time-22)/.65))));
 }
 function pause(){playing=false;cancelAnimationFrame(animation);render();}
 function tick(now){
  if(!playing)return;const oldPhase=phase;time=Math.min(playUntil,camera.advance(time,(now-lastTime)/1000,Number($('speed').value)));lastTime=now;render();
  if(phase!==oldPhase)$('announcement').textContent=phases[phase]+'. '+narrative();
  if(time>=playUntil){pause();$('announcement').textContent=(time>=27?'Replay complete. ':'Candidate ready for comparison. ')+narrative();}else animation=requestAnimationFrame(tick);
 }
 function play(until=27){cancelAnimationFrame(animation);playUntil=until;if(inspector.opened){inspector.close(false);$('play-toggle').focus({preventScroll:true});}if(time>=27)time=0;playing=true;lastTime=performance.now();render();animation=requestAnimationFrame(tick);}
 function seek(value,announce=true){pause();time=Math.max(0,Math.min(27,value));render();if(announce)$('announcement').textContent=phases[phase]+'. '+narrative();}
 function writeURL(mode='pushState'){
  const url=new URL(location.href);url.searchParams.set('case',scenario.default_case_id);url.searchParams.set('rank',String(selected.rank));url.searchParams.delete('t');history[mode]({time},'',url);
 }
 function chooseCandidate(id,investigate=false,preserveTime=false,writeHistory=true){
  const candidate=scenario.candidates.find(c=>c.case_id===id);if(!candidate)return;pause();selected=candidate;caseSelections.set(scenario.default_case_id,id);if(!preserveTime)time=investigate?(reduced.matches?16:14.2):camera.anchors[3];updateCandidate();inspector.changed();render();if(writeHistory)writeURL();$('announcement').textContent=`Selected recorded rank ${selected.rank}. ${selected.candidate.title}`;
  if(investigate&&!reduced.matches)play(16);
 }
 function chooseCase(index,writeHistory=true){
  pause();scenario=data.scenarios[index];selected=scenario.candidates.find(c=>c.case_id===(caseSelections.get(scenario.default_case_id)||scenario.default_case_id))||scenario.candidates[0];time=0;mount();inspector.changed();render();if(writeHistory)writeURL();
 }
 function restoreURL(state={}){
  const parameters=new URLSearchParams(location.search),caseId=parameters.get('case');
  let index=data.scenarios.findIndex(s=>s.default_case_id===caseId);
  if(index<0)index=0;
  scenario=data.scenarios[index];$('case-select').value=String(index);
  const rank=Number(parameters.get('rank'));
  const candidate=scenario.candidates.find(c=>c.rank===rank)||scenario.candidates.find(c=>c.case_id===scenario.default_case_id)||scenario.candidates[0];
  chooseCase(index,false);if(candidate.case_id!==selected.case_id)chooseCandidate(candidate.case_id,false,true,false);
  const requestedTime=Number(state.time??parameters.get('t'));if(Number.isFinite(requestedTime))seek(requestedTime,false);
  writeURL('replaceState');
 }
 async function load(){
  $('load-error').hidden=true;
  try{
   data=freeze(await loadJSON());$('case-select').replaceChildren(...data.scenarios.map((s,i)=>{const option=el('option',caseLabels[i]||s.label);option.value=String(i);return option;}));$('case-select').disabled=false;
   $('phase-select').replaceChildren(...phases.map((p,i)=>{const option=el('option',String(i+1).padStart(2,'0')+' · '+['Source','Query','Retrieval','Candidates','Compare','Verdict'][i]);option.value=String(i);option.setAttribute('aria-label',p);return option;}));
   $('load-status').hidden=true;$('stage-shell').hidden=false;$('playback').hidden=false;
   inspector=new window.CiteProbeInspector({context:()=>({data,scenario,selected}),state:()=>({time,caseId:selected.case_id}),pause,resize:()=>render(),select:id=>chooseCandidate(id,false,true)});
   $('open-evidence').disabled=false;
   restoreURL();
   window.replayV3={get state(){return {time,phase,playing,caseId:selected.case_id,rank:selected.rank,title:selected.candidate.title,doi:selected.candidate.doi,verdict:selected.outputs.C.verdict,reducedMotion:reduced.matches};},seek:t=>seek(t,false)};
   document.fonts.ready.then(()=>{layoutMetrics.width=0;render();});
  }catch(error){$('load-status').hidden=true;$('load-error').hidden=false;$('load-error-message').textContent=error.message;}
 }
 $('play-toggle').addEventListener('click',()=>playing?pause():play());$('restart').addEventListener('click',()=>{seek(0,false);play();});$('previous').addEventListener('click',()=>seek(camera.anchors[Math.max(0,phase-1)]));$('next').addEventListener('click',()=>seek(camera.anchors[Math.min(5,phase+1)]));
 $('timeline').addEventListener('input',()=>seek(Number($('timeline').value),false));$('phase-select').addEventListener('change',()=>seek(camera.anchors[Number($('phase-select').value)]));
 $('case-select').addEventListener('change',()=>chooseCase(Number($('case-select').value)));$('retry-load').addEventListener('click',load);
 window.addEventListener('popstate',event=>{if(data)restoreURL(event.state||{});});
 $('open-evidence').addEventListener('click',event=>inspector.open('record',event.currentTarget));$('inspect-stage').addEventListener('click',event=>inspector.open('record',event.currentTarget));$('verdict-evidence').addEventListener('click',event=>inspector.open('record',event.currentTarget));
 reduced.addEventListener('change',()=>{pause();render();});window.addEventListener('resize',()=>{layoutMetrics.width=0;render();});document.addEventListener('visibilitychange',()=>{if(document.hidden&&playing)pause();});new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{resizeFrame=0;render();});}).observe($('viewport'));
 load();
})();
