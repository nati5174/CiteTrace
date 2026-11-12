/* Presentation only: grouping, directed traces and obstacle-aware orthogonal routing. */
(function(root){
 'use strict';
 const names={DOI_EXISTENCE_IS_NOT_IDENTITY:'Registration check',METADATA_COMPARISON:'Metadata',MAIN_TEXT_CONCORDANCE:'Main-text check',DISJOINT_RESEARCH_OBJECTS:'Abstract checks'};
 const outcome=v=>v==='CORRECT'?'Same work':v==='INCORRECT'?'Different work':'Identity unresolved';
 function describe(n){
  const d=n.detail||{};
  if(n.kind==='source')return {title:'Intended paper',subtitle:n.label||'Metadata removed',kind:'paper'};
  if(n.kind==='candidate')return {title:'Retrieved paper',subtitle:n.label||'Metadata removed',kind:'paper'};
  if(n.kind==='verdict')return {title:d.verdict,subtitle:outcome(d.verdict),kind:'verdict'};
  if(n.kind==='comparison')return {title:names[d.code]||'Recorded check',subtitle:'Verification',kind:'check'};
  if(n.kind==='missing')return {title:'Evidence missing',subtitle:'Unmet requirement',kind:'missing'};
  if(n.kind==='registration')return {title:'DOI record',subtitle:'Registration',kind:'registration'};
  const kind=n.kind==='full_text'?'Full text':n.kind==='abstract'?'Abstract':n.kind==='relationship'?'Version link':'Evidence';
  return {title:(d.side==='SOURCE'?'Source ':d.side==='CANDIDATE'?'Candidate ':'')+kind.toLowerCase(),subtitle:d.origin==='INDEXED'?'Not primary':d.used_by_rule?'Used in check':'Available only',kind:d.origin==='INDEXED'?'excluded':d.used_by_rule?'used':'available'};
 }
 function model(graph,expanded=false){
  const verdict=graph.nodes.find(n=>n.kind==='verdict'),nodes=[],owner=new Map();
  function add(id,members,title,subtitle,kind,band){
   if(!members.length)return;const n={id,members:members.map(n=>n.id),title,subtitle,kind,band};nodes.push(n);members.forEach(v=>owner.set(v.id,id));
  }
  if(expanded){
   graph.nodes.forEach(n=>{const d=describe(n);if(n.kind==='registration'&&verdict.detail.doi_existence==='EXISTS')d.title='DOI exists';add(n.id,[n],d.title,d.subtitle,d.kind,['source','candidate'].includes(n.kind)?0:n.kind==='comparison'?2:['missing','verdict'].includes(n.kind)?3:1);});
  }else{
   graph.nodes.filter(n=>['source','candidate'].includes(n.kind)).forEach(n=>{const d=describe(n);add(n.id,[n],d.title,d.subtitle,d.kind,0);});
   const evidence=graph.nodes.filter(n=>n.detail?.evidence_id);
   const registrations=evidence.filter(n=>n.kind==='registration');
   add('@registration',registrations,verdict.detail.doi_existence==='EXISTS'?'DOI exists':'DOI record','Registration only','registration',1);
   const other=evidence.filter(n=>n.kind!=='registration');
   const used=other.filter(n=>n.detail.used_by_rule&&n.detail.origin!=='INDEXED');
   const available=other.filter(n=>!n.detail.used_by_rule&&n.detail.origin!=='INDEXED');
   const excluded=other.filter(n=>n.detail.origin==='INDEXED');
   const summary=ns=>ns.every(n=>n.kind==='full_text')?'Full text':ns.every(n=>n.kind==='abstract')?'Primary abstracts':'Used evidence';
   add('@used',used,summary(used),'Used in verification','used',1);
   add('@available',available,'Available only',available.length===1?describe(available[0]).title:`${available.length} records · not used`,'available',1);
   add('@excluded',excluded,'Indexed evidence','Not primary evidence','excluded',1);
   const checks=graph.nodes.filter(n=>n.kind==='comparison');
   const decisive=checks.find(n=>['MAIN_TEXT_CONCORDANCE','DISJOINT_RESEARCH_OBJECTS'].includes(n.detail.code));
   add('@checks',checks,decisive?names[decisive.detail.code]:checks.some(n=>n.detail.code==='METADATA_COMPARISON')?'Metadata':'DOI check','Recorded checks','check',2);
   const missing=graph.nodes.filter(n=>n.kind==='missing');
   add('@missing',missing,'Evidence missing',missing.some(n=>/primary/i.test(n.detail.reason))?'Primary evidence needed':'More evidence needed','missing',3);
   add(verdict.id,[verdict],verdict.detail.verdict,outcome(verdict.detail.verdict),'verdict',3);
  }
  // Any unfamiliar future record stays accessible instead of disappearing in grouping.
  graph.nodes.filter(n=>!owner.has(n.id)).forEach(n=>{const d=describe(n);add(n.id,[n],d.title,d.subtitle,d.kind,1);});
  // Arrange captured evidence nearer its recorded paper without changing the records.
  const position=n=>{const sides=new Set(n.members.map(id=>graph.nodes.find(v=>v.id===id).detail.side));return sides.has('SOURCE')?(sides.has('CANDIDATE')?1:0):2;};
  nodes.sort((a,b)=>a.band-b.band||(a.band===1?position(a)-position(b)||(a.kind==='used'?0:a.kind==='available'?1:2)-(b.kind==='used'?0:b.kind==='available'?1:2):0));
  const buckets=new Map(),internal=[];
  graph.edges.forEach((e,index)=>{const source=owner.get(e.source),target=owner.get(e.target);if(source===target){internal.push(index);return;}const key=JSON.stringify([source,target]);if(!buckets.has(key))buckets.set(key,{id:'link-'+index,source,target,indices:[],relations:[]});const edge=buckets.get(key);edge.indices.push(index);if(!edge.relations.includes(e.relation))edge.relations.push(e.relation);});
  return {nodes,edges:[...buckets.values()],internal,owner:Object.fromEntries(owner),verdict:verdict.detail};
 }
 function trace(graph,seeds){
  const seen=new Set(seeds),edges=new Set();
  // Walk ancestors and descendants separately. Do not traverse sideways via a shared verdict.
  for(const reverse of [true,false]){const visited=new Set(seeds),queue=[...seeds];while(queue.length){const id=queue.shift();graph.edges.forEach((e,i)=>{if((reverse?e.target:e.source)!==id)return;edges.add(i);const next=reverse?e.source:e.target;seen.add(next);if(!visited.has(next)){visited.add(next);queue.push(next);}});}}
  return {nodes:graph.nodes.filter(n=>seen.has(n.id)).map(n=>n.id),edges:graph.edges.map((_,i)=>i).filter(i=>edges.has(i))};
 }
 function widths(view,width){
  const mobile=width<700,w=Math.max(140,Math.min(920,width)),margin=mobile?24:32,gap=mobile?24:48;
  const result={};
  for(let band=0;band<4;band++){
   const items=view.nodes.filter(n=>n.band===band),columns=mobile?1:Math.min(3,items.length);
   const base=(w-margin*2-gap*Math.max(0,columns-1))/Math.max(1,columns);
   items.forEach(n=>result[n.id]=mobile&&n.kind==='verdict'?w-24:Math.min(mobile?base:n.kind==='verdict'?360:n.kind==='paper'?300:280,base));
  }
  return {width:w,mobile,margin,gap,values:result};
 }
 function layout(view,width,heights={}){
  const spec=widths(view,width),rects={},rows=[];let y=20;
  for(let band=0;band<4;band++){
   const items=view.nodes.filter(n=>n.band===band),columns=spec.mobile?1:Math.min(3,items.length);
   for(let offset=0;offset<items.length;offset+=Math.max(1,columns)){
    const row=items.slice(offset,offset+columns),height=Math.max(...row.map(n=>heights[n.id]||(n.kind==='paper'?112:n.kind==='verdict'?104:84)));
    const sum=row.reduce((s,n)=>s+spec.values[n.id],0)+spec.gap*(row.length-1);let x=(spec.width-sum)/2;
    row.forEach(n=>{const h=heights[n.id]||(n.kind==='paper'?112:n.kind==='verdict'?104:84);rects[n.id]={x,y:y+(height-h)/2,width:spec.values[n.id],height:h};x+=spec.values[n.id]+spec.gap;});
    rows.push({top:y,bottom:y+height});y+=height+(spec.mobile?40:56);
   }
  }
  return {width:spec.width,height:y-(spec.mobile?40:56)+20,rects,rows,mobile:spec.mobile};
 }
 const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
 function hits(a,b,r){
  if(a.x===b.x)return a.x>r.x+.01&&a.x<r.x+r.width-.01&&Math.max(a.y,b.y)>r.y+.01&&Math.min(a.y,b.y)<r.y+r.height-.01;
  return a.y>r.y+.01&&a.y<r.y+r.height-.01&&Math.max(a.x,b.x)>r.x+.01&&Math.min(a.x,b.x)<r.x+r.width-.01;
 }
 function crossing(a,b,c,d){
  if(a.x===b.x&&c.y===d.y)return a.x>Math.min(c.x,d.x)+.1&&a.x<Math.max(c.x,d.x)-.1&&c.y>Math.min(a.y,b.y)+.1&&c.y<Math.max(a.y,b.y)-.1;
  if(a.y===b.y&&c.x===d.x)return crossing(c,d,a,b);
  return false;
 }
 function sharedLength(a,b,c,d){
  if(a.x===b.x&&c.x===d.x&&a.x===c.x)return Math.max(0,Math.min(Math.max(a.y,b.y),Math.max(c.y,d.y))-Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y)));
  if(a.y===b.y&&c.y===d.y&&a.y===c.y)return Math.max(0,Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x))-Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x)));
  return 0;
 }
 function neighbor(id,key,rects){
  const a=rects[id],vertical=['ArrowUp','ArrowDown'].includes(key),sign=['ArrowUp','ArrowLeft'].includes(key)?-1:1;
  const candidates=Object.entries(rects).filter(([other])=>other!==id).map(([other,r])=>{const dx=r.x+r.width/2-a.x-a.width/2,dy=r.y+r.height/2-a.y-a.height/2;return {id:other,forward:(vertical?dy:dx)*sign,lateral:Math.abs(vertical?dx:dy),cost:Math.hypot(dx,dy)+Math.abs(vertical?dx:dy)};}).filter(v=>v.forward>1);
  const aligned=candidates.filter(v=>v.forward>=v.lateral);return (aligned.length?aligned:candidates).sort((a,b)=>a.cost-b.cost)[0]?.id;
 }
 class Heap{
  constructor(){this.items=[];}
  push(v){let i=this.items.push(v)-1;while(i){const p=(i-1)>>1;if(this.items[p].cost<=v.cost)break;this.items[i]=this.items[p];i=p;}this.items[i]=v;}
  pop(){const first=this.items[0],last=this.items.pop();if(this.items.length){let i=0;while(i*2+1<this.items.length){let j=i*2+1;if(j+1<this.items.length&&this.items[j+1].cost<this.items[j].cost)j++;if(this.items[j].cost>=last.cost)break;this.items[i]=this.items[j];i=j;}this.items[i]=last;}return first;}
 }
 function route(view,geometry){
  const rs=geometry.rects,obstacles=Object.values(rs).map(r=>({x:r.x-8,y:r.y-8,width:r.width+16,height:r.height+16}));
  const xs=new Set([8,16,geometry.width-16,geometry.width-8]),ys=new Set([4,geometry.height-4]);
  Object.values(rs).forEach(r=>{[r.x-20,r.x+r.width+20,r.x+r.width/2].forEach(x=>xs.add(x));[r.y-20,r.y+r.height+20,r.y+r.height/2].forEach(y=>ys.add(y));});
  geometry.rows.slice(0,-1).forEach((r,i)=>ys.add((r.bottom+geometry.rows[i+1].top)/2));
  const previous=[],routed=new Map();
  const sorted=[...view.edges].sort((a,b)=>{
   const priority=e=>e.target==='verdict'?0:e.relations.includes('used_in_computation')?1:2;
   return priority(a)-priority(b)||view.edges.indexOf(a)-view.edges.indexOf(b);
  });
  for(const edge of sorted){
   const a=rs[edge.source],b=rs[edge.target],sameRow=Math.abs(a.y+a.height/2-b.y-b.height/2)<Math.min(a.height,b.height)/2;
   let start,end,from,to;
   if(sameRow){const right=b.x>a.x;start={x:right?a.x+a.width:a.x,y:a.y+a.height/2};end={x:right?b.x:b.x+b.width,y:b.y+b.height/2};from={x:start.x+(right?20:-20),y:start.y};to={x:end.x+(right?-20:20),y:end.y};}
   else{const down=b.y>a.y;start={x:a.x+a.width/2,y:down?a.y+a.height:a.y};end={x:b.x+b.width/2,y:down?b.y:b.y+b.height};from={x:start.x,y:start.y+(down?20:-20)};to={x:end.x,y:end.y+(down?-20:20)};}
   const xx=[...new Set([...xs,from.x,to.x])].filter(x=>x>=4&&x<=geometry.width-4).sort((a,b)=>a-b),yy=[...new Set([...ys,from.y,to.y])].filter(y=>y>=4&&y<=geometry.height-4).sort((a,b)=>a-b),ny=yy.length;
   const sx=xx.indexOf(from.x),sy=yy.indexOf(from.y),tx=xx.indexOf(to.x),ty=yy.indexOf(to.y),heap=new Heap(),best=new Map(),parent=new Map();
   const key=(x,y,d)=>(x*ny+y)*3+d;const first=key(sx,sy,0);heap.push({x:sx,y:sy,d:0,g:0,cost:0,key:first});best.set(first,0);let final;
   const cache=new Map();
   while(heap.items.length){
    const current=heap.pop();if(current.g!==best.get(current.key))continue;
    if(current.x===tx&&current.y===ty){final=current;break;}
    for(const [dx,dy] of [[-1,0],[1,0],[0,-1],[0,1]]){
     const x=current.x+dx,y=current.y+dy;if(x<0||y<0||x>=xx.length||y>=yy.length)continue;
     const p={x:xx[current.x],y:yy[current.y]},q={x:xx[x],y:yy[y]},dir=dx?1:2;
     const segmentKey=[Math.min(current.x,x),Math.min(current.y,y),Math.max(current.x,x),Math.max(current.y,y)].join(',');
     if(!cache.has(segmentKey))cache.set(segmentKey,obstacles.some(r=>hits(p,q,r)));
     if(cache.get(segmentKey))continue;
     let crosses=0,shared=0;for(const previousEdge of previous){const points=previousEdge.points;for(let i=1;i<points.length;i++){if(crossing(p,q,points[i-1],points[i]))crosses++;if(previousEdge.source!==edge.source&&previousEdge.target!==edge.target){const length=sharedLength(p,q,points[i-1],points[i]);if(length)shared+=80+length*.6;}}}
     const g=current.g+Math.abs(q.x-p.x)+Math.abs(q.y-p.y)+(current.d&&current.d!==dir?24:0)+crosses*350+shared;
     const k=key(x,y,dir);if(g>=(best.get(k)??Infinity))continue;best.set(k,g);parent.set(k,current);heap.push({x,y,d:dir,g,cost:g+Math.abs(q.x-to.x)+Math.abs(q.y-to.y),key:k});
    }
   }
   if(!final)throw Error('No unobstructed recorded-link route: '+edge.id);
   const points=[];let c=final;while(c){points.push({x:xx[c.x],y:yy[c.y]});c=parent.get(c.key);}points.reverse();points.unshift(start);points.push(end);
   const compact=points.filter((p,i)=>i===0||p.x!==points[i-1].x||p.y!==points[i-1].y).filter((p,i,arr)=>i===0||i===arr.length-1||!((arr[i-1].x===p.x&&arr[i+1].x===p.x)||(arr[i-1].y===p.y&&arr[i+1].y===p.y)));
   routed.set(edge.id,compact);previous.push({...edge,points:compact});
  }
  return view.edges.map(e=>({...e,points:routed.get(e.id)}));
 }
 function path(points){
  let result=`M${points[0].x},${points[0].y}`;
  for(let i=1;i<points.length-1;i++){
   const a=points[i-1],b=points[i],c=points[i+1],r=Math.min(8,Math.hypot(b.x-a.x,b.y-a.y)/2,Math.hypot(c.x-b.x,c.y-b.y)/2);
   const lengthA=Math.hypot(b.x-a.x,b.y-a.y),lengthB=Math.hypot(c.x-b.x,c.y-b.y);
   const p={x:b.x+(a.x-b.x)*r/lengthA,y:b.y+(a.y-b.y)*r/lengthA},q={x:b.x+(c.x-b.x)*r/lengthB,y:b.y+(c.y-b.y)*r/lengthB};
   result+=` L${p.x},${p.y} Q${b.x},${b.y} ${q.x},${q.y}`;
  }
  return result+` L${points.at(-1).x},${points.at(-1).y}`;
 }
 root.CiteProbeEvidenceLayout=Object.freeze({model,trace,widths,layout,route,path,hits,overlap,describe,neighbor});
})(typeof window==='undefined'?globalThis:window);
