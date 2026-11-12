/* Interactive view of existing provenance. No identity rules or evidence are generated here. */
(function(root){
 'use strict';
 const L=root.CiteProbeEvidenceLayout,{el,safeLink,disclosure}=root.CiteProbeUI;
 const NS='http://www.w3.org/2000/svg';
 const label={A:'Registration',B:'Metadata',C:'Evidence'};
 const relation={compared_with:'Compared with',recorded_evidence:'Recorded capture',used_in_computation:'Used in this check',input_metadata:'Metadata input',informs_provisional_rule_result:'Informs recorded result',limits_decision:'Limits the decision'};
 const iconPaths={paper:'M5 3h9l5 5v13H5zM14 3v5h5M8 12h8M8 16h8',registration:'M8 13l5-5M9 8l2-2a4 4 0 016 6l-2 2M15 16l-2 2a4 4 0 01-6-6l2-2',used:'M5 5h14v14H5zM8 12l3 3 5-6',available:'M5 4h14v16H5zM8 8h8M8 12h8M8 16h5',excluded:'M4 5h16l-6 7v7l-4-2v-5zM4 21L21 4',check:'M5 5h6v6H5zM13 13h6v6h-6zM13 8h6M16 5v6M5 16h6',missing:'M12 3a9 9 0 100 18 9 9 0 000-18M9 9a3 3 0 116 0c0 2-3 2-3 4M12 16v1',verdict:'M7 3h10l4 9-4 9H7l-4-9zM8 12h8'};
 function icon(kind){const svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','24');svg.setAttribute('height','24');svg.setAttribute('aria-hidden','true');const p=document.createElementNS(NS,'path');p.setAttribute('d',iconPaths[kind]||iconPaths.available);p.setAttribute('fill','none');p.setAttribute('stroke','currentColor');p.setAttribute('stroke-width','1.6');p.setAttribute('stroke-linejoin','round');p.setAttribute('stroke-linecap','round');svg.append(p);return svg;}
 const memberName=n=>n.kind==='source'?'Intended paper':n.kind==='candidate'?'Retrieved paper':n.kind==='missing'?'Missing requirement':n.kind==='verdict'?n.detail.verdict:n.detail.side?`${n.detail.side==='SOURCE'?'Source':'Candidate'} ${n.kind.replaceAll('_',' ')}`:L.describe(n).title;
 const summaries={DOI_EXISTENCE_IS_NOT_IDENTITY:'Registration does not establish paper identity.',METADATA_COMPARISON:'Compares recorded titles, authors, years and identifiers.',MAIN_TEXT_CONCORDANCE:'Recorded main text agrees after documented normalization.',DISJOINT_RESEARCH_OBJECTS:'The recorded rule found different research objects.'};
 class EvidenceMap{
  constructor(options){
   this.options=options;this.graph=options.graph;this.expanded=false;this.selection=[];this.zoom=1;this.pan={x:0,y:0};this.width=0;this.panEnabled=false;this.drag=null;this.buttons=new Map();
   this.root=el('section',undefined,'em-shell');this.root.dataset.caseId=options.selected.case_id;
   const heading=el('header',undefined,'em-heading'),decision=this.graph.nodes.find(n=>n.kind==='verdict').detail;
   this.decision=decision;const verdict=el('span',`${options.recomputed?'Recomputed':'Recorded'} ${options.approach} · ${decision.verdict}`,'em-result');verdict.dataset.verdict=decision.verdict;
   heading.append(el('h2','Evidence map'),verdict);
   const statement=options.approach==='A'?'DOI registration is not paper identity.':decision.verdict==='ABSTAIN'?(decision.doi_existence==='EXISTS'?'DOI exists. Paper identity unresolved.':'Paper identity is unresolved.'):decision.verdict==='CORRECT'?'Evidence supports the same work.':'Evidence supports different work.';
   this.root.append(heading,el('p',statement,'em-story'));
   const toolbar=el('div',undefined,'em-controls');toolbar.setAttribute('role','group');toolbar.setAttribute('aria-label','Evidence graph controls');
   const verifierLabel=el('label',undefined,'em-verifier'),select=el('select');verifierLabel.append(el('span','Verifier','sr-only'),select);select.id='trace-approach';
   for(const a of ['A','B','C']){const option=el('option',`${a} · ${label[a]}`);option.value=a;select.append(option);}select.value=options.approach;select.addEventListener('change',()=>options.approachChanged(select.value));toolbar.append(verifierLabel);
   if(options.hasCounterfactual){const lab=el('label',undefined,'em-verifier'),s=el('select');lab.append(el('span','Evidence set','sr-only'),s);s.id='trace-evidence';for(const [value,text] of [['recorded','Recorded'],['counterfactual',options.recomputedLabel||'Last Python run']]){const option=el('option',text);option.value=value;s.append(option);}s.value=options.recomputed?'counterfactual':'recorded';s.addEventListener('change',()=>options.scopeChanged(s.value));toolbar.append(lab);}
   const button=(text,id,action)=>{const b=el('button',text);b.type='button';b.dataset.action=id;b.addEventListener('click',action);toolbar.append(b);return b;};
   button('Fit graph','fit',()=>this.fit());
   for(const [text,id,sign] of [['Zoom in','in',1],['Zoom out','out',-1]]){const b=button(text,id,()=>this.setZoom(this.zoom+sign*.15));b.setAttribute('aria-label',text);b.title=text;const svg=icon('registration');svg.querySelector('path').setAttribute('d',sign===1?'M5 12h14M12 5v14':'M5 12h14');b.replaceChildren(svg);}
   this.readout=el('output','100%','em-zoom');this.readout.setAttribute('aria-label','Graph zoom');toolbar.append(this.readout);
   button('Reset','reset',()=>{this.clear();this.expanded=false;this.panEnabled=false;this.move.setAttribute('aria-pressed','false');this.viewport.dataset.pan='false';this.renderNodes();});
   this.expand=button('Full map','records',()=>{this.clear();this.expanded=!this.expanded;this.renderNodes();});this.expand.setAttribute('aria-pressed','false');
   this.move=button('Move view','pan',()=>{this.panEnabled=!this.panEnabled;this.move.setAttribute('aria-pressed',String(this.panEnabled));this.viewport.dataset.pan=String(this.panEnabled);});this.move.setAttribute('aria-pressed','false');this.move.setAttribute('aria-label','Move view: enable touch dragging');this.move.title='Move view';const moveIcon=icon('registration');moveIcon.querySelector('path').setAttribute('d','M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3');this.move.replaceChildren(moveIcon);this.root.append(toolbar);
   this.selectionBar=el('div',undefined,'em-selection');this.selectionBar.hidden=true;this.selectionHeading=el('strong');this.selectionNote=el('span');const selectedCopy=el('div');selectedCopy.append(this.selectionHeading,this.selectionNote);
   const open=el('button','Details');open.addEventListener('click',()=>{this.detail.style.scrollMarginTop=(this.railHeight()+16)+'px';this.detail.scrollIntoView({block:'start'});});const clear=el('button','Clear');clear.addEventListener('click',()=>this.clear());this.selectionBar.append(selectedCopy,open,clear);this.root.append(this.selectionBar);
   this.viewport=el('div',undefined,'em-viewport');this.viewport.tabIndex=0;this.viewport.setAttribute('role','region');this.viewport.setAttribute('aria-label','Interactive evidence graph. Tab to nodes. Arrow keys move the view; plus and minus zoom; Home fits the graph.');
   this.world=el('div',undefined,'em-world');this.svg=document.createElementNS(NS,'svg');this.svg.setAttribute('aria-hidden','true');this.world.append(this.svg);this.viewport.append(this.world);this.root.append(this.viewport);
   const hint=el('p','Provisional · Select to trace recorded links, not causation.','em-hint');this.root.append(hint);
   this.detail=el('section',undefined,'em-detail');this.detail.hidden=true;this.detail.setAttribute('aria-label','Selected evidence details');this.root.append(this.detail);
   this.announce=el('p',undefined,'sr-only');this.announce.setAttribute('role','status');this.root.append(this.announce);
   this.root.append(disclosure('Advanced details · complete recorded graph',this.graph));options.host.append(this.root);
   this.viewport.addEventListener('keydown',e=>this.key(e));
   this.viewport.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('button')||(e.pointerType==='touch'&&!this.panEnabled))return;this.drag={x:e.clientX,y:e.clientY,pan:{...this.pan}};this.viewport.setPointerCapture(e.pointerId);this.viewport.dataset.dragging='true';e.preventDefault();});
   this.viewport.addEventListener('pointermove',e=>{if(!this.drag)return;const ratio=this.viewport.getBoundingClientRect().width/this.viewport.clientWidth;this.pan={x:this.drag.pan.x+(e.clientX-this.drag.x)/ratio,y:this.drag.pan.y+(e.clientY-this.drag.y)/ratio};this.transform();});
   const stop=()=>{this.drag=null;this.viewport.dataset.dragging='false';};this.viewport.addEventListener('pointerup',stop);this.viewport.addEventListener('pointercancel',stop);
   this.renderNodes();this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(this.root.closest('#inspector'));document.fonts.ready.then(()=>{if(this.root.isConnected)this.resize(true);});
  }
  renderNodes(){
   this.view=L.model(this.graph,this.expanded);this.buttons.forEach(b=>b.remove());this.buttons.clear();this.width=0;this.expand.setAttribute('aria-pressed',String(this.expanded));
   this.view.nodes.forEach(n=>{const b=el('button',undefined,'em-node');b.type='button';b.dataset.viewId=n.id;b.dataset.members=JSON.stringify(n.members);b.dataset.kind=n.kind;b.setAttribute('aria-label',n.title+'. '+n.members.map(id=>this.graph.nodes.find(v=>v.id===id).label).join('. '));b.title=n.members.map(id=>this.graph.nodes.find(v=>v.id===id).label).join('\n');
    b.append(icon(n.kind));if(n.kind==='paper'){const fold=el('span',undefined,'fold');fold.setAttribute('aria-hidden','true');b.append(fold);}const text=el('span',undefined,'em-node-copy');text.append(el('strong',n.title),el('span',n.subtitle,'em-subtitle'));b.append(text);
    if(n.kind==='verdict')b.dataset.verdict=this.decision.verdict;
    b.addEventListener('click',()=>this.select(n.members));b.addEventListener('focus',()=>{this.reveal(n.id);b.style.scrollMarginTop=(this.railHeight()+8)+'px';b.scrollIntoView({block:'nearest',inline:'nearest'});});this.buttons.set(n.id,b);this.world.append(b);
   });
   this.resize(true);if(this.selection.length)this.select(this.selection);else this.highlight();
  }
  resize(force=false){
   const width=this.viewport.clientWidth;if(!width)return;const modal=this.root.closest('#inspector'),available=modal.clientHeight-modal.querySelector('header').offsetHeight;this.root.dataset.rail=available>340&&width>240?'sticky':'inline';if(!force&&this.width===width)return;this.width=width;this.world.style.transform='none';
   const spec=L.widths(this.view,width-16),heights={};this.viewport.dataset.narrow=String(spec.mobile);this.viewport.dataset.tiny=String(width<260);
   this.buttons.forEach((b,id)=>{b.style.width=spec.values[id]+'px';b.style.height='auto';b.style.transform='none';});
   const ratio=this.viewport.getBoundingClientRect().width/width;
   this.buttons.forEach((b,id)=>heights[id]=Math.ceil(b.getBoundingClientRect().height/ratio));
   this.geometry=L.layout(this.view,width-16,heights);this.routes=L.route(this.view,this.geometry);
   this.world.style.width=this.geometry.width+'px';this.world.style.height=this.geometry.height+'px';this.svg.setAttribute('width',String(this.geometry.width));this.svg.setAttribute('height',String(this.geometry.height));this.svg.setAttribute('viewBox',`0 0 ${this.geometry.width} ${this.geometry.height}`);
   this.buttons.forEach((b,id)=>{const r=this.geometry.rects[id];b.style.width=r.width+'px';b.style.height=r.height+'px';b.style.transform=`translate(${r.x}px,${r.y}px)`;});
   this.svg.replaceChildren();const defs=document.createElementNS(NS,'defs'),gradient=document.createElementNS(NS,'linearGradient');gradient.id='em-gradient';gradient.setAttribute('gradientUnits','userSpaceOnUse');gradient.setAttribute('x2',String(this.geometry.width));gradient.setAttribute('y2',String(this.geometry.height));for(const [offset,color] of [['0%','#7561e8'],['100%','#c558c4']]){const stop=document.createElementNS(NS,'stop');stop.setAttribute('offset',offset);stop.setAttribute('stop-color',color);gradient.append(stop);}defs.append(gradient);
   const marker=document.createElementNS(NS,'marker');marker.id='em-arrow';marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','8');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','5');marker.setAttribute('markerHeight','5');marker.setAttribute('orient','auto');const arrow=document.createElementNS(NS,'path');arrow.setAttribute('d','M2 1L7 5L2 9');arrow.setAttribute('fill','none');arrow.setAttribute('stroke','#7561e8');marker.append(arrow);defs.append(marker);this.svg.append(defs);
   this.routes.forEach(e=>{const p=document.createElementNS(NS,'path');p.classList.add('em-link');p.dataset.linkId=e.id;p.dataset.edgeIndices=JSON.stringify(e.indices);p.dataset.source=e.source;p.dataset.target=e.target;p.setAttribute('d',L.path(e.points));p.setAttribute('marker-end','url(#em-arrow)');p.setAttribute('vector-effect','non-scaling-stroke');if(e.relations.includes('limits_decision'))p.classList.add('em-limit');else if(e.relations.every(r=>r==='recorded_evidence'))p.classList.add('em-capture');const title=document.createElementNS(NS,'title');title.textContent=e.indices.map(i=>relation[this.graph.edges[i].relation]||this.graph.edges[i].relation).join('; ');p.append(title);this.svg.append(p);});
   this.viewport.style.height=(this.geometry.height+24)+'px';this.fit();this.highlight();
  }
  fit(){this.zoom=1;this.pan={x:0,y:0};this.transform();}
  setZoom(value){const next=Math.max(.9,Math.min(1.8,Math.round(value*100)/100)),w=this.viewport.clientWidth,h=this.viewport.clientHeight,base=(w-this.geometry.width)/2;const old=this.zoom;this.pan.x=w/2-base-(w/2-base-this.pan.x)*(next/old);this.pan.y=h/2-12-(h/2-12-this.pan.y)*(next/old);this.zoom=next;this.transform();}
  transform(){
   if(!this.geometry)return;const w=this.viewport.clientWidth,h=this.viewport.clientHeight,baseX=(w-this.geometry.width)/2;
   this.pan.x=Math.max(-this.geometry.width*this.zoom+64-baseX,Math.min(w-64-baseX,this.pan.x));this.pan.y=Math.max(-this.geometry.height*this.zoom+52,Math.min(h-76,this.pan.y));
   this.tx=baseX+this.pan.x;this.ty=12+this.pan.y;this.world.style.transform=`translate(${this.tx}px,${this.ty}px) scale(${this.zoom})`;this.readout.textContent=Math.round(this.zoom*100)+'%';this.root.dataset.zoom=String(this.zoom);
  }
  reveal(id){
   if(!this.geometry)return;const r=this.geometry.rects[id],w=this.viewport.clientWidth,h=this.viewport.clientHeight;const x=this.tx+r.x*this.zoom,y=this.ty+r.y*this.zoom;
   if(x<8)this.pan.x+=8-x;else if(x+r.width*this.zoom>w-8)this.pan.x-=x+r.width*this.zoom-w+8;
   if(y<8)this.pan.y+=8-y;else if(y+r.height*this.zoom>h-8)this.pan.y-=y+r.height*this.zoom-h+8;this.transform();
  }
  key(e){
   if(e.ctrlKey||e.metaKey||e.altKey)return;
   const b=e.target.closest('.em-node');
   if(b&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){
    e.preventDefault();e.stopPropagation();const next=L.neighbor(b.dataset.viewId,e.key,this.geometry.rects);if(next)this.buttons.get(next).focus({preventScroll:true});return;
   }
   if(b)return;
   if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();this.pan.x+=e.key==='ArrowLeft'?32:e.key==='ArrowRight'?-32:0;this.pan.y+=e.key==='ArrowUp'?32:e.key==='ArrowDown'?-32:0;this.transform();}
   if(['+','=','-','Home','0'].includes(e.key)){e.preventDefault();if(e.key==='Home'||e.key==='0')this.fit();else this.setZoom(this.zoom+(e.key==='-'?-.15:.15));}
  }
  select(ids){
   if(!this.expanded&&ids.length===1){const group=this.view.nodes.find(n=>n.members.includes(ids[0]));if(group?.members.length>1){this.selection=[...ids];this.expanded=true;this.renderNodes();this.buttons.get(ids[0])?.focus({preventScroll:true});return;}}
   this.selection=ids.filter(id=>this.graph.nodes.some(n=>n.id===id));this.highlight();this.detail.replaceChildren();this.detail.hidden=false;
   const nodes=this.selection.map(id=>this.graph.nodes.find(n=>n.id===id));if(!nodes.length)return;
   const selected=this.view.nodes.find(n=>n.members.some(id=>this.selection.includes(id))),heading=nodes.length===1?memberName(nodes[0]):selected.title;
   this.detail.append(el('h3',heading));this.selectionBar.hidden=false;this.selectionHeading.textContent=heading;
   const usage=nodes.some(n=>n.detail.origin==='INDEXED')?'Indexed evidence is excluded as primary.':nodes.some(n=>n.kind==='missing')?'An unmet requirement, not evidence that the paper is wrong.':nodes.some(n=>n.detail.used_by_rule)?'Used by this verifier.':nodes.some(n=>n.detail.evidence_id)?'Recorded, but not used by this verifier.':null;
   const note=usage||summaries[nodes[0].detail.code]||(nodes[0].kind==='verdict'?'Provisional machine output.':'Recorded paper metadata.');this.selectionNote.textContent=note;
   this.detail.append(el('p',note,'em-detail-note'));
   if(nodes.length>1){const records=el('div',undefined,'em-member-list');nodes.forEach(n=>{const b=el('button',memberName(n));b.addEventListener('click',()=>this.select([n.id]));records.append(b);});this.detail.append(records);}
   for(const n of nodes){const d=n.detail;if(n.kind==='source'||n.kind==='candidate'){this.detail.append(el('p',n.label));if(d.doi||d.arxiv_id)this.detail.append(el('p',d.doi||'arXiv:'+d.arxiv_id,'mono'));if(d.doi)this.detail.append(safeLink('Open DOI','https://doi.org/'+d.doi));if(d.arxiv_id)this.detail.append(safeLink('Open arXiv record','https://arxiv.org/abs/'+d.arxiv_id));}
    if(n.kind==='missing')this.detail.append(el('p',d.reason));
    if(n.kind==='verdict')this.detail.append(el('p',`${d.verdict} · Provisional machine output.`));
    if(d.url)this.detail.append(safeLink((nodes.length>1?memberName(n)+' · ':'')+'Recorded source',d.url));if(d.artifact_available&&d.evidence_id)this.detail.append(safeLink((nodes.length>1?memberName(n)+' ? ':'')+'Archived capture','/api/artifact?id='+encodeURIComponent(d.evidence_id)));
    const details=el('details',undefined,'em-record-detail');details.append(el('summary','Recorded details'));if(d.authors?.length)details.append(el('p',d.authors.join('; ')));for(const key of ['explanation','reason','excerpt','locator'])if(d[key])details.append(el('p',d[key]));if(d.retrieved_at)details.append(el('p','Retrieved: '+d.retrieved_at));if(d.complete_main_text!==undefined&&n.kind==='full_text')details.append(el('p',d.complete_main_text?'Marked complete in the recorded evidence.':'Completeness not established.'));if(d.missing_evidence?.length)details.append(el('p',d.missing_evidence.join('; ')));details.append(disclosure('Advanced details · exact record',d));this.detail.append(details);
   }
   const connections=this.graph.edges.filter(e=>this.selection.includes(e.source)||this.selection.includes(e.target));
   const links=el('div',undefined,'em-related');connections.forEach(e=>{const outgoing=this.selection.includes(e.source),other=this.graph.nodes.find(n=>n.id===(outgoing?e.target:e.source));const b=el('button',`${outgoing?'To':'From'} ${memberName(other)} · ${relation[e.relation]||e.relation}`);b.addEventListener('click',()=>this.select([other.id]));links.append(b);});if(links.children.length){const more=el('details',undefined,'em-record-detail');more.append(el('summary','Recorded connections'),links);this.detail.append(more);}
   const back=el('button','Return to graph');back.addEventListener('click',()=>{const id=this.view.owner[this.selection[0]];this.reveal(id);this.buttons.get(id)?.scrollIntoView({block:'center'});this.buttons.get(id)?.focus({preventScroll:true});});this.detail.append(back);this.announce.textContent=heading+'. Recorded upstream and downstream links highlighted.';
  }
  clear(){const returnFocus=this.selectionBar.contains(document.activeElement);this.selection=[];this.detail.hidden=true;this.selectionBar.hidden=true;this.highlight();if(returnFocus)this.viewport.focus({preventScroll:true});}
  highlight(){
   const traced=this.selection.length?L.trace(this.graph,this.selection):null,edges=new Set(traced?.edges||[]),nodes=new Set(traced?.nodes||[]);
   this.root.dataset.tracing=String(Boolean(traced));
   this.svg.querySelectorAll('.em-link').forEach(p=>{const highlighted=JSON.parse(p.dataset.edgeIndices).filter(i=>edges.has(i));p.dataset.highlightedIndices=JSON.stringify(highlighted);p.classList.toggle('em-traced',highlighted.length>0);});
   this.buttons.forEach((b,id)=>{const model=this.view.nodes.find(n=>n.id===id);b.classList.toggle('em-related-node',model.members.some(id=>nodes.has(id)));const selected=model.members.some(id=>this.selection.includes(id));b.setAttribute('aria-pressed',String(selected));});
   this.root.dataset.selection=JSON.stringify(this.selection);
  }
  railHeight(){return this.root.dataset.rail==='sticky'&&!this.selectionBar.hidden?this.selectionBar.offsetHeight:0;}
  destroy(){this.observer?.disconnect();this.drag=null;this.width=0;}
 }
 root.CiteProbeEvidenceMap=EvidenceMap;
})(window);
