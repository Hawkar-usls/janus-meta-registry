function consolidate(input) {
  const {start,end,nodes,runs}=input, s=Date.parse(start), e=Date.parse(end);
  if(!Number.isFinite(s)||!Number.isFinite(e)||e-s!==86400000) throw Error("WINDOW");
  const ids=new Map(), rejected={unlisted:0,ineligible:0,duplicate:0,conflict:0};
  for(const x of runs){
    const n=Object.keys(nodes).find(k=>nodes[k].repo===x.repo);
    if(!n||!nodes[n].paths.includes(x.path)){rejected.unlisted++;continue;}
    if(!Number.isSafeInteger(x.id)||x.id<=0||x.event!=="schedule"||x.branch!=="main"||x.status!=="completed"||x.conclusion!=="success"||!Number.isFinite(Date.parse(x.updated))||Date.parse(x.updated)>e){rejected.ineligible++;continue;}
    const k=x.repo+":"+x.id, old=ids.get(k);
    if(old){if(old.path!==x.path){rejected.conflict++;throw Error("ID_CONFLICT");}rejected.duplicate++;if(Date.parse(old.updated)>=Date.parse(x.updated))continue;}
    ids.set(k,x);
  }
  const out={start,end,rejected,nodes:{}};
  for(const [n,c] of Object.entries(nodes)){
    const all=[...ids.values()].filter(x=>x.repo===c.repo).sort((a,b)=>Date.parse(a.updated)-Date.parse(b.updated));
    const win=all.filter(x=>Date.parse(x.updated)>=s&&Date.parse(x.updated)<=e);
    const points=[s,...win.map(x=>Date.parse(x.updated)),e];
    const gaps=points.slice(1).map((x,i)=>x-points[i]);
    const bins=new Set(win.map(x=>Math.min(23,Math.floor((Date.parse(x.updated)-s)/3600000))));
    const single=c.paths.map(p=>({path:p,last_success:all.filter(x=>x.path===p).at(-1)??null,count:win.filter(x=>x.path===p).length}));
    out.nodes[n]={last_success:all.at(-1)??null,by_source:single,unique_success:win.length,hours_covered:bins.size,max_silence_seconds:Math.round(Math.max(...gaps)/1000),max_internal_gap_seconds:win.length>1?Math.round(Math.max(...win.slice(1).map((x,i)=>Date.parse(x.updated)-Date.parse(win[i].updated)))/1000):null,events:win,pass:bins.size===24&&Math.max(...gaps)<=3600000};
  }
  return out;
}
if(typeof module!=='undefined')module.exports={consolidate};
