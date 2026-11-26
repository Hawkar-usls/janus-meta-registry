// R5 epigenesis fixed-seed benchmark; node benchmark.js
const families=["balanced","forward_fanout","reverse_fanout","dense","chain","cyclic","tree_like","bottleneck"];
  function graph(f,k){
    let seed=201001+families.indexOf(f)*1000+k;
    function rand(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296}
    const pick=n=>Math.floor(rand()*n), depth=8+pick(7), positive=k%2===0;
    const layers=[], meta=[], edges=[], seen=new Set();
    for(let l=0;l<=depth;l++){
      let width=l===0||l===depth?1:f==="chain"?1:f==="tree_like"?Math.min(120,Math.pow(2,Math.min(l,depth-l))):f==="bottleneck"?(l===Math.floor(depth/2)?1:45):f==="dense"?22+pick(8):f==="forward_fanout"?Math.min(65,2+Math.floor(4*Math.pow(l,1.25))):f==="reverse_fanout"?Math.min(65,2+Math.floor(4*Math.pow(depth-l,1.25))):12+pick(15);
      layers[l]=[];for(let i=0;i<width;i++){let id=meta.length;layers[l].push(id);meta.push([l,pick(5),pick(6),pick(20),pick(4)])}
    }
    const cut=Math.floor(depth/2), s=0,t=meta.length-1;
    function add(u,v,valid){let key=u+":"+v;if(seen.has(key))return;seen.add(key);if(!positive&&meta[u][0]<=cut&&meta[v][0]>cut)valid=false;edges.push([u,v,valid])}
    const spine=layers.map(a=>a[pick(a.length)]);
    if(positive)for(let l=0;l<depth;l++)add(spine[l],spine[l+1],true);
    for(let l=0;l<depth;l++)for(const u of layers[l]){
      let b=layers[l+1],degree=f==="dense"?b.length:f==="chain"?1:f==="forward_fanout"?5:f==="reverse_fanout"?3:f==="tree_like"?2:f==="bottleneck"?5:2+pick(5);
      if(f==="dense")for(const v of b)add(u,v,rand()<.85);
      else for(let j=0;j<degree;j++)add(u,b[pick(b.length)],rand()<.88);
      if(f==="cyclic"){for(let j=0;j<2;j++)add(u,layers[l][pick(layers[l].length)],rand()<.85);if(l>0)add(u,layers[l-1][pick(layers[l-1].length)],rand()<.85)}
    }
    // Fixed random ordering for all consumers.
    for(let i=edges.length-1;i>0;i--){let j=pick(i+1);[edges[i],edges[j]]=[edges[j],edges[i]]}
    return {meta,edges,s,t,positive};
  }


function run(graph,families){
 const methods=["plain","chromosome","global_r4","freq_fixed","freq_global","selective_fixed","selective_global","epigenesis"],workloads=["shared_source","shared_target","mixed_reuse","phase_shift"];
 const blank=()=>({correct:0,invalid:0,stale:0,stale_versions:0,budget_violations:0,audited_distances:0,common:0,query:0,maintenance:0,witness:0,cache:0,evictions:0,rebuilds:0,retained_updates:0,repaired_updates:0,peak_nodes:0,pre_eviction_peak:0,forward_queries:0,reverse_queries:0,bypasses:0,admission_misses:0,cache_hits:0});
 const group=()=>Object.fromEntries(methods.map(m=>[m,blank()])),totals=group(),by_family={},by_workload={},cases=[];
 for(const f of families)by_family[f]=group();for(const w of workloads)by_workload[w]=group();
 const cost=c=>c.common+c.query+c.maintenance+c.witness+c.cache;
 function scenario(g,seed,w){
  let state=(seed^0x7f4a7c15)>>>0;const pick=n=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return Math.floor(state/4294967296*n)};
  const n=g.meta.length,live=new Set(g.edges.filter(e=>e[2]).map(([u,v])=>u*n+v)),sp=[0,pick(n),pick(n)],tp=[n-1,pick(n),pick(n)],timeline=[];
  for(let ep=0;ep<8;ep++){
   if(ep>0){const arr=[...live],key=arr[pick(arr.length)];if(key===undefined)throw Error("empty delete");live.delete(key);timeline.push({op:"delete",u:Math.floor(key/n),v:key%n});let u,v;do{u=pick(n);v=pick(n)}while(u===v||live.has(u*n+v));live.add(u*n+v);timeline.push({op:"insert",u,v})}
   let mode=w==="phase_shift"?(ep<4?"shared_source":"shared_target"):w;
   for(let i=0;i<8;i++){let s=mode==="shared_source"?0:mode==="shared_target"?pick(n):i%4===0?pick(n):sp[pick(3)],t=mode==="shared_target"?n-1:mode==="shared_source"?pick(n):i%4===0?pick(n):tp[pick(3)];timeline.push({op:"query",s,t})}
  }return timeline
 }
 function oracle(n,live,start,rev){const d=Array(n).fill(Infinity);d[start]=0;for(let i=0;i<n-1;i++){let change=false;for(const key of live){let u=Math.floor(key/n),v=key%n;if(rev)[u,v]=[v,u];if(d[u]+1<d[v]){d[v]=d[u]+1;change=true}}if(!change)break}return d}
 function execute(g,timeline,m,refs){
  const c=blank(),n=g.meta.length,a=Array.from({length:n},()=>new Set()),b=Array.from({length:n},()=>new Set()),live=new Set(),dual=m!=="plain",bounded=dual,repairMode=dual,global=["global_r4","freq_global","selective_global","epigenesis"].includes(m),freq=["freq_fixed","freq_global","selective_fixed","selective_global","epigenesis"].includes(m),selective=["selective_fixed","selective_global","epigenesis"].includes(m);
  const shards=[{rev:false,cap:dual?n:0,entries:new Map(),size:0},{rev:true,cap:dual?n:bounded?2*n:Infinity,entries:new Map(),size:0}];
  let version=0,prev=null,clock=0,history=[];
  for(const [u,v,ok] of g.edges){c.common++;if(ok){a[u].add(v);b[v].add(u);live.add(u*n+v);c.common+=2}}
  const dist=(tr,v)=>tr.d.get(v)??Infinity;
  function bfs(root,target,adj){let d=new Map([[root,0]]),p=new Map([[root,null]]),q=[root];c.query++;for(let h=0;h<q.length;h++){if(target!==null&&d.has(target))break;let u=q[h];c.query++;for(const v of adj[u]){c.query++;if(d.has(v))continue;d.set(v,d.get(u)+1);p.set(v,u);q.push(v);c.query++;if(v===target)break}}return {d,p,version}}
  function repair(tr,u,v,op,adj,inc){
   c.maintenance++;
   if(op==="insert"){
    if(!(dist(tr,u)+1<dist(tr,v))){c.retained_updates++;return}
    let q=[v];tr.d.set(v,dist(tr,u)+1);tr.p.set(v,u);c.maintenance++;c.repaired_updates++;
    for(let h=0;h<q.length;h++){let x=q[h];c.maintenance++;for(const y of adj[x]){c.maintenance++;let z=dist(tr,x)+1;if(z<dist(tr,y)){tr.d.set(y,z);tr.p.set(y,x);q.push(y);c.maintenance++}}}return
   }
   if(tr.p.get(v)!==u){c.retained_updates++;return}
   c.repaired_updates++;const bad=new Set([v]),q=[v];c.maintenance++;
   for(let h=0;h<q.length;h++){let x=q[h];c.maintenance++;for(const y of adj[x]){c.maintenance++;if(tr.p.get(y)===x&&!bad.has(y)){bad.add(y);q.push(y);c.maintenance++}}}
   for(const x of bad){tr.d.delete(x);tr.p.delete(x);c.maintenance++}
   const relax=[];
   for(const x of bad){c.maintenance++;let best=Infinity,parent=null;for(const y of inc[x]){c.maintenance++;if(!bad.has(y)&&dist(tr,y)+1<best){best=dist(tr,y)+1;parent=y}}if(parent!==null){tr.d.set(x,best);tr.p.set(x,parent);relax.push(x);c.maintenance++}}
   for(let h=0;h<relax.length;h++){let x=relax[h];c.maintenance++;for(const y of adj[x]){c.maintenance++;if(!bad.has(y))continue;let z=dist(tr,x)+1;if(z<dist(tr,y)){tr.d.set(y,z);tr.p.set(y,x);relax.push(y);c.maintenance++}}}
  }
  const size=()=>shards[0].size+shards[1].size;
  function evict(sh){c.pre_eviction_peak=Math.max(c.pre_eviction_peak,size());if(global){while(size()>2*n){let choices=[];for(const a of shards){c.cache++;if(a.entries.size){let [key,tr]=a.entries.entries().next().value;choices.push({a,key,tr})}}c.cache++;let x=choices.length===1||choices[0].tr.touch<=choices[1].tr.touch?choices[0]:choices[1];x.a.entries.delete(x.key);x.a.size-=x.tr.d.size;c.evictions++;c.cache++}}else while(sh.size>sh.cap){let [key,tr]=sh.entries.entries().next().value;sh.entries.delete(key);sh.size-=tr.d.size;c.evictions++;c.cache++}}
  for(let i=0;i<timeline.length;i++){
   const e=timeline[i],ref=refs[i];
   function truth(root,rev){let key=(rev?"R":"F")+root;if(!ref.has(key))ref.set(key,oracle(n,live,root,rev));return ref.get(key)}
   if(e.op!=="query"){
    const {u,v,op}=e,key=u*n+v;if(op==="insert"){a[u].add(v);b[v].add(u);live.add(key)}else{a[u].delete(v);b[v].delete(u);live.delete(key)}c.common+=2;version++;
    for(const sh of shards){if(m==="plain"||(!dual&&!sh.rev))continue;
     if(m==="lru_reset"){c.maintenance++;sh.entries.clear();sh.size=0;continue}
     const x=sh.rev?v:u,y=sh.rev?u:v,adj=sh.rev?b:a,inc=sh.rev?a:b;
     for(const [root,tr] of sh.entries){let before=tr.d.size;
      if(repairMode){repair(tr,x,y,op,adj,inc);sh.size+=tr.d.size-before}
      else{c.maintenance++;const affect=op==="delete"?tr.p.get(y)===x:dist(tr,x)+1<dist(tr,y);if(affect){sh.entries.delete(root);sh.size-=before;c.maintenance++;continue}c.retained_updates++}
      tr.version=version;c.maintenance++;
     }evict(sh)
    }
   }else{
    const {s,t}=e;let rev=m!=="plain";
    let bypass=m==="epigenesis"&&n<=16,admit=true;
    if(dual&&!bypass){c.cache+=3;const f=shards[0].entries.has(s),z=shards[1].entries.has(t);
     if(!freq)rev=z||(!f&&!(prev&&prev.s===s&&prev.t!==t));
     else if(f||z)rev=z;
     else {let fc=0,rc=0;for(const q of history){c.cache+=2;fc+=+(q.s===s);rc+=+(q.t===t)}c.cache++;if(fc===rc){c.cache+=2;rev=b[t].size<=a[s].size}else rev=rc>fc;if(selective&&!(rev?rc:fc))admit=false}
    }else if(bypass){rev=false;c.bypasses++}
    if(rev)c.reverse_queries++;else c.forward_queries++;
    const root=rev?t:s,target=rev?s:t,adj=rev?b:a,sh=shards[+rev];let tr;
    if(m==="plain"||bypass||!admit){tr=bfs(root,target,adj);if(!admit)c.admission_misses++}
    else{c.cache++;tr=sh.entries.get(root);if(!tr){tr=bfs(root,null,adj);sh.entries.set(root,tr);sh.size+=tr.d.size;c.rebuilds++;c.cache++}else if(bounded){sh.entries.delete(root);sh.entries.set(root,tr);c.cache++;c.cache_hits++}if(global){tr.touch=++clock;c.cache++}
     if(tr.version!==version)c.stale_versions++;evict(sh);
    }
    let p=null;if(tr.d.has(target)){p=[];let u=target,guard=0;while(u!==null&&guard++<=n){p.push(u);u=tr.p.get(u)}if(u!==null)p=null;else if(!rev)p.reverse()}
    c.witness+=p?Math.max(0,p.length-1):0;let valid=!p||p[0]===s&&p.at(-1)===t&&p.slice(1).every((v,j)=>live.has(p[j]*n+v)),len=p?p.length-1:Infinity;c.invalid+=+!valid;c.correct+=+(valid&&len===truth(s,false)[t]);prev={s,t};if(freq&&!bypass){history.push({s,t});c.cache++;if(history.length>8){history.shift();c.cache++}}
   }
   c.peak_nodes=Math.max(c.peak_nodes,size());c.pre_eviction_peak=Math.max(c.pre_eviction_peak,size());
   if(global&&size()>2*n)c.budget_violations++;for(const sh of shards){if(!global&&sh.size>sh.cap)c.budget_violations++;for(const [root,tr] of sh.entries){if(tr.version!==version)c.stale_versions++;let d=truth(root,sh.rev);for(let k=0;k<n;k++){c.audited_distances++;if(dist(tr,k)!==d[k])c.stale++}}}
  }return c
 }
 for(const f of families)for(let k=0;k<16;k++){let seed=201001+1000*families.indexOf(f)+k,g=graph(f,k),w=workloads[k%4],timeline=scenario(g,seed,w),refs=timeline.map(()=>new Map()),rec={family:f,seed,workload:w,nodes:g.meta.length,edges:g.edges.length,timeline,methods:{}};for(const m of methods){const c=execute(g,timeline,m,refs);rec.methods[m]={...c,total:cost(c)};for(const acc of [totals[m],by_family[f][m],by_workload[w][m]])for(const key in c)acc[key]+=c[key]}cases.push(rec)}
 function compare(x){const costs=Object.fromEntries(methods.map(m=>[m,cost(x[m])])),best=methods.filter(m=>m!=="plain"&&m!=="epigenesis").sort((a,b)=>costs[a]-costs[b])[0];return {costs,best_bounded:best,epigenesis_vs_r4:1-costs.epigenesis/costs.chromosome,epigenesis_vs_best:1-costs.epigenesis/costs[best],memory_reduction:1-x.epigenesis.peak_nodes/x.chromosome.peak_nodes}}
 const comparisons={all:compare(totals),by_family:Object.fromEntries(families.map(f=>[f,compare(by_family[f])])),by_workload:Object.fromEntries(workloads.map(w=>[w,compare(by_workload[w])]))};
 const primary=methods.every(m=>totals[m].correct===8192&&!totals[m].invalid&&!totals[m].stale&&!totals[m].stale_versions&&!totals[m].budget_violations),q=comparisons.all,secondary=q.epigenesis_vs_r4>=.10&&q.epigenesis_vs_best>=0&&q.memory_reduction>=-.20&&comparisons.by_family.chain.epigenesis_vs_r4>=0&&comparisons.by_workload.mixed_reuse.epigenesis_vs_r4>=0;
 return {id:"JANUS-CHRONO-DNA-R5-EPIGENESIS",protocol_commit:"afbd1ebaf4dfc8d4fa323f63156bbab3be38779b",status:primary&&secondary?"SYNTHETIC_EPIGENESIS_GATE_PASS__EXTERNAL_HOLD":primary?"CORRECTNESS_PASS__EFFICIENCY_HOLD":"CORRECTNESS_FAIL",primary,secondary,graphs:cases.length,queries:8192,mutations:1792,totals,comparisons,by_family,by_workload,cases:cases.map(({timeline,...rest})=>rest),limitations:["Fixed generator lineage, author-created not independent","Budget caps resident cached distance entries; temporary and index memory excluded","Abstract counters not runtime, not actual RAM; oracle audit excluded equally","All policies use same R3 repair; no native JANUS module or biology tested","Case timelines deterministically regenerated by benchmark, omitted from result for size"]};
}
console.log(JSON.stringify(run(graph,families),null,2));
