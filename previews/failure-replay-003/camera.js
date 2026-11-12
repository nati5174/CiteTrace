/* Pure choreography: one replay time, shared objects and a bounds-led camera. */
(function(root){
 'use strict';
 const starts=Object.freeze([0,4,8,11,16,22]);
 const anchors=Object.freeze([2,6,10,13.8,20.8,25]);
 const clamp=x=>Math.max(0,Math.min(1,x));
 const smooth=x=>{x=clamp(x);return x*x*(3-2*x);};
 const mix=(a,b,p)=>a+(b-a)*p;
 function phaseAt(t){let phase=0;starts.forEach((v,i)=>{if(t>=v)phase=i;});return phase;}
 function bezier(a,b,c,d,t){const s=1-t;return {x:s*s*s*a.x+3*s*s*t*b.x+3*s*t*t*c.x+t*t*t*d.x,y:s*s*s*a.y+3*s*s*t*b.y+3*s*t*t*c.y+t*t*t*d.y};}
 function path(p){return `M${p[0].x},${p[0].y} C${p[1].x},${p[1].y} ${p[2].x},${p[2].y} ${p[3].x},${p[3].y}`;}
 function link(a,b,vertical=false,bend=0){return vertical?[a,{x:a.x+bend,y:(a.y+b.y)/2},{x:b.x+bend,y:(a.y+b.y)/2},b]:[a,{x:(a.x+b.x)/2,y:a.y+bend},{x:(a.x+b.x)/2,y:b.y+bend},b];}
 function rect(a,b,p){return {x:mix(a.x,b.x,p),y:mix(a.y,b.y,p),width:mix(a.width,b.width,p),height:mix(a.height,b.height,p)};}
 function bounds(rs){const x=Math.min(...rs.map(r=>r.x)),y=Math.min(...rs.map(r=>r.y));return {x,y,width:Math.max(...rs.map(r=>r.x+r.width))-x,height:Math.max(...rs.map(r=>r.y+r.height))-y};}
 function constrain(camera,rs,area){
  const box=bounds(rs),scale=Math.min(camera.scale,area.width/box.width,area.height/box.height);
  const tx=Math.max(area.x-box.x*scale,Math.min(area.x+area.width-(box.x+box.width)*scale,area.x+area.width/2-camera.x*scale));
  const ty=Math.max(area.y-box.y*scale,Math.min(area.y+area.height-(box.y+box.height)*scale,area.y+area.height/2-camera.y*scale));
  return {x:(area.x+area.width/2-tx)/scale,y:(area.y+area.height/2-ty)/scale,scale,tx,ty};
 }
 function frame(time,width,height,rank,reduced=false,metrics={}){
  const phase=phaseAt(time),t=reduced?anchors[phase]:time,narrow=width<900;
  const progress=(a,b)=>smooth((t-a)/(b-a));
  const opening=progress(1.7,3.2),collapse=progress(7.8,9.4),handoff=progress(14.2,16);
  const introWidth=narrow?Math.min(370,width-36):440;
  const contextWidth=narrow?introWidth:width>1100?310:240;
  const contextHeight=narrow?100:300,providerWidth=narrow?170:width>1100?170:150;
  const gap=narrow?20:width>1100?44:28;
  const sourceIntro={x:0,y:0,width:introWidth,height:350};
  const sourceQuery={x:0,y:0,width:introWidth,height:narrow?280:350};
  const sourceContext={x:0,y:narrow?0:162,width:contextWidth,height:contextHeight};
  const beforeFlow=rect(sourceIntro,sourceQuery,opening);
  const beforeCompare=rect(beforeFlow,sourceContext,collapse);
  const cmpWidth=narrow?width-32:Math.min(440,(width-112)/2);
  const sourceCompare={x:0,y:0,width:cmpWidth,height:narrow?100:340};
  const source=rect(beforeCompare,sourceCompare,handoff);
  const providerQuery=narrow?{x:(introWidth-providerWidth)/2,y:sourceQuery.height+96,width:providerWidth,height:100}:{x:introWidth+64,y:(350-112)/2,width:providerWidth,height:112};
  const compactWidth=narrow?Math.max(150,width-100):Math.min(440,Math.max(320,width-contextWidth-providerWidth-gap-160));
  const rowHeight=narrow?144:112,rowGap=16,fanHeight=5*rowHeight+4*rowGap;
  const providerFlow=narrow?{x:0,y:contextHeight+24,width:providerWidth,height:100}:{x:contextWidth+gap,y:(fanHeight-112)/2,width:providerWidth,height:112};
  const provider=rect(providerQuery,providerFlow,collapse);
  const providerOpacity=progress(3.2,3.9)*(1-progress(14.2,15.6));
  const baseX=narrow?64:providerFlow.x+providerFlow.width+100;
  const baseY=narrow?providerFlow.y+providerFlow.height+32:0;
  const compareCandidate={x:narrow?0:cmpWidth+72,y:narrow?114:0,width:cmpWidth,height:narrow?Math.max(198,metrics.comparisonHeight??0,metrics.candidateHeight??0):340};
  const providerPort={x:provider.x+(narrow?8:provider.width/2),y:provider.y+provider.height/2};
  // Rank order is spatial order. Every landing slot is disjoint and remains
  // visible through the overview; selection never replaces or restacks results.
  const stack=Array.from({length:5},(_,i)=>({x:baseX,y:baseY+i*(rowHeight+rowGap),width:compactWidth,height:rowHeight}));
  const cards=stack.map((target,i)=>{
   const selected=i+1===rank,birth=progress(8+i*.48,9.1+i*.48);
   const landing=target;
   const endpoint={x:landing.x+landing.width/2,y:landing.y+landing.height/2};
   const points=narrow?[providerPort,{x:8,y:endpoint.y},{x:8,y:endpoint.y},endpoint]:[providerPort,{x:provider.x+provider.width+56,y:endpoint.y},{x:baseX-40,y:endpoint.y},endpoint];
   const center=bezier(...points,birth),scale=mix(.12,1,birth);
   const emitted={x:center.x-target.width*scale/2,y:center.y-target.height*scale/2,width:target.width*scale,height:target.height*scale};
   const position=selected?rect(emitted,compareCandidate,handoff):emitted;
   const actualScale=selected?mix(scale,1,handoff):scale;
   const opacity=progress(8+i*.48,8.22+i*.48)*(selected?1:1-progress(14.2,15.2));
   return {...position,contentWidth:position.width/actualScale,contentHeight:position.height/actualScale,scale:actualScale,rank:i+1,selected,opacity,path:points,reveal:birth,zIndex:selected?30:i+3};
  });
  const queryStart=narrow?{x:source.x+source.width-8,y:source.y+source.height-8}:{x:source.x+source.width-8,y:source.y+source.height/2};
  const queryEnd=narrow?{x:provider.x+provider.width-8,y:provider.y+provider.height/2}:{x:provider.x+8,y:provider.y+provider.height/2};
  const lane=Math.max(source.x+source.width,provider.x+provider.width)+40,midY=(queryStart.y+queryEnd.y)/2;
  let queryPath=narrow?[queryStart,{x:lane,y:midY},{x:lane,y:midY},queryEnd]:link(queryStart,queryEnd);
  if(narrow){const settled=link({x:source.x+source.width/2,y:source.y+source.height},{x:provider.x+provider.width/2,y:provider.y},true);queryPath=queryPath.map((p,i)=>({x:mix(p.x,settled[i].x,progress(8.15,9.4)),y:mix(p.y,settled[i].y,progress(8.15,9.4))}));}
  const queryCorridor=bounds(Array.from({length:41},(_,i)=>{const p=bezier(...queryPath,i/40);return {x:p.x-10,y:p.y-10,width:20,height:20};}));
  const queryProgress=progress(4,7.75);
  const query=bezier(...queryPath,queryProgress);
  const labelWidth=Math.min(narrow?240:260,width-(narrow?52:24));
  const queryLabel={x:narrow?(source.width-labelWidth)/2:providerQuery.x+(providerWidth-labelWidth)/2,y:narrow?sourceQuery.height+6:18,width:labelWidth,height:84};
  const queryOpacity=progress(3.25,3.8)*(1-progress(7.8,8.15));
  const packetOpacity=progress(3.95,4.15)*(1-progress(7.75,8));
  const selected=cards[rank-1],comparisonBounds=bounds([source,selected]);
  const sourceEvidence={x:sourceCompare.x,y:sourceCompare.y+sourceCompare.height+16,width:sourceCompare.width,height:80};
  const candidateEvidence={x:compareCandidate.x,y:compareCandidate.y+compareCandidate.height+16,width:compareCandidate.width,height:80};
  const showEvidence=!narrow;
  const evidenceBounds=bounds([source,selected,...(showEvidence?[sourceEvidence,candidateEvidence]:[])]);
  const evidenceFocus=rect(comparisonBounds,evidenceBounds,progress(18,18.8));
  const flowObjects=[source,provider,...stack];
  const flowBounds=bounds(flowObjects);
  const introFocus=rect(sourceIntro,bounds([source,providerQuery,queryLabel,queryCorridor]),opening);
  const queryBounds=bounds([source,provider,queryLabel,queryCorridor]);
  const retrievalFocus=rect(queryBounds,flowBounds,collapse);
  let focus=t<4?introFocus:t<7.8?queryBounds:rect(retrievalFocus,comparisonBounds,handoff);
  if(t>=16)focus=evidenceFocus;
  const ranks=(metrics.ranksHeight??76)*progress(9.5,11)*(1-progress(14.2,16));
  const checks=(metrics.checksHeight??110)*progress(14.2,16);
  const reserve=ranks+checks,padding=narrow?12:24;
  const area={x:padding,y:padding,width:Math.max(80,width-padding*2),height:Math.max(80,height-reserve-padding*2)};
  const desired={x:focus.x+focus.width/2,y:focus.y+focus.height/2,scale:Math.min(1.04,area.width/focus.width,area.height/focus.height)};
  const active=['source'];
  if(t>=4&&t<14.2)active.push('provider');
  if(t>=8)active.push('candidate');
  if(t>=18.8&&showEvidence)active.push('source-evidence','candidate-evidence');
  const objects={source,provider,candidate:selected,'source-evidence':sourceEvidence,'candidate-evidence':candidateEvidence};
  const guarded=[...active.map(id=>objects[id]),...(t>=8&&t<16?cards.filter(c=>c.opacity>.001):[])];
  if(queryOpacity>.001)guarded.push(queryLabel,queryCorridor);
  const camera=constrain(desired,guarded,area);
  const targetScale=Math.min(t<16?mix(.9,1,collapse):.85,area.width/focus.width);
  const minimumHeight=Math.max(420,focus.height*targetScale+reserve+padding*2+12);
  const worldSize={width:Math.ceil(Math.max(introWidth+64,cmpWidth*(narrow?1:2)+72,...stack.map(r=>r.x+r.width)))+32,height:Math.ceil(Math.max(476,sourceEvidence.y+80,candidateEvidence.y+80,...stack.map(r=>r.y+r.height)))+32};
  return {phase,narrow,source,provider,cards,query,queryPath,queryProgress,queryDraw:progress(1.7,3.2),queryLabel,queryOpacity,packetOpacity,providerOpacity,worldSize,
   queryVisible:queryOpacity>.001,comparison:handoff,camera,active,safeArea:area,minimumHeight,
   compactSource:narrow&&t>=7.8,compactCandidates:t>=7.8&&t<16,sourceFont:narrow?mix(24,18,collapse):mix(mix(28,width>1100?26:22,collapse),28,handoff),
   sourceEvidence,candidateEvidence,showEvidence,evidenceOpacity:progress(18.8,19.4),candidateEvidenceOpacity:progress(19.1,19.7),
   reviewField:t>=16&&t<17.5?'titles':t>=17.5&&t<18.8?'identifiers':t>=18.8&&t<22?'evidence':'',
   checksVisible:phase===4,verdictVisible:phase===5};
 }
 root.CiteProbeCamera=Object.freeze({starts,anchors,phaseAt,frame,path,bezier,bounds,constrain,advance:(t,delta,speed)=>Math.min(27,t+Math.max(0,Math.min(delta,.2))*speed)});
})(typeof window==='undefined'?globalThis:window);
