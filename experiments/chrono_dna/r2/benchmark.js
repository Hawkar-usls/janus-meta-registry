// R2 selective replication deterministic exam; node benchmark.js
const families=["balanced","forward_fanout","reverse_fanout","dense","chain","cyclic","tree_like","bottleneck"];
  function graph(f,k){
    let seed=91001+families.indexOf(f)*1000+k;
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
  function oracle(g){let d=Array(g.meta.length).fill(Infinity);d[g.s]=0;for(let j=0;j<g.meta.length-1;j++){let change=false;for(const [u,v,ok] of g.edges)if(ok&&d[u]+1<d[v]){d[v]=d[u]+1;change=true}if(!change)break}return Number.isFinite(d[g.t])?d[g.t]:null}


function run(graph,oracle,families){
 const workloads=["unique_mixed","shared_source","shared_target","mixed_reuse"],methods=["filtered_forward","cached_forward","cached_reverse","selective","pair_cache"];
 const blank=()=>({correct:0,invalid:0,index:0,search:0,cache:0,witness:0,space_peak:0,reverse_builds:0,reverse_queries:0});
 const totals=Object.fromEntries(methods.map(m=>[m,blank()])),by_workload={},by_family={},cases=[];
 const group=()=>Object.fromEntries(methods.map(m=>[m,blank()]));
 for(const w of workloads)by_workload[w]=group();for(const f of families)by_family[f]=group();
 const cost=c=>c.index+c.search+c.cache+c.witness;
 function queryList(g,seed,w){
  let state=(seed^0x9e3779b9)>>>0;const pick=n=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return Math.floor(state/4294967296*n)};
  const n=g.meta.length,q=[],sPool=[0,pick(n),pick(n)],tPool=[n-1,pick(n),pick(n)],seen=new Set();
  for(let i=0;i<24;i++){let s,t;
   if(w==="shared_source"){s=0;t=pick(n)}
   else if(w==="shared_target"){s=pick(n);t=n-1}
   else if(w==="mixed_reuse"){s=i%3===0?pick(n):sPool[pick(3)];t=i%4===0?pick(n):tPool[pick(3)]}
   else {let tries=0;do{s=pick(n);t=pick(n);tries++}while(seen.has(s+":"+t)&&tries<128)}
   seen.add(s+":"+t);q.push([s,t])
  }return q
 }
 function execute(g,qs,m){
  const c=blank(),n=g.meta.length,fw=new Map(),rw=new Map(),pairs=new Map(),sf=new Map(),tf=new Map();let a=null,b=null,retained=0;
  function build(reverse){let arr=Array.from({length:n},()=>[]);for(const [u,v,ok] of g.edges){c.index++;if(ok){arr[reverse?v:u].push(reverse?u:v);c.index++}}if(reverse)c.reverse_builds++;return arr}
  if(m!=="cached_reverse")a=build(false);else b=build(true);
  function tree(start){c.search++;return {p:new Map([[start,null]]),q:[start],head:0,pos:0}}
  function advance(tr,adj,target){
   while(!tr.p.has(target)&&tr.head<tr.q.length){
    const u=tr.q[tr.head];if(tr.pos===0)c.search++;
    if(tr.pos>=adj[u].length){tr.head++;tr.pos=0;continue}
    const v=adj[u][tr.pos++];c.search++;if(tr.p.has(v))continue;c.search++;tr.p.set(v,u);tr.q.push(v);
   }
   if(!tr.p.has(target))return null;let p=[],u=target;while(u!==null){p.push(u);u=tr.p.get(u)}return p
  }
  function cached(store,adj,start,target,reverse){
   c.cache++;let tr=store.get(start);if(!tr){tr=tree(start);store.set(start,tr);retained++}
   const before=tr.p.size,p=advance(tr,adj,target);retained+=tr.p.size-before;c.space_peak=Math.max(c.space_peak,retained);return p?(reverse?p:p.reverse()):null
  }
  function plain(s,t){const tr=tree(s),p=advance(tr,a,t);c.space_peak=Math.max(c.space_peak,retained+tr.p.size);return p?p.reverse():null}
  const answers=[];
  for(const [s,t] of qs){let p;
   if(m==="filtered_forward")p=plain(s,t);
   else if(m==="cached_forward")p=cached(fw,a,s,t,false);
   else if(m==="cached_reverse"){c.reverse_queries++;p=cached(rw,b,t,s,true)}
   else if(m==="pair_cache"){const key=s+":"+t;c.cache++;if(pairs.has(key))p=pairs.get(key);else{p=plain(s,t);pairs.set(key,p);retained+=p?p.length:1;c.space_peak=Math.max(c.space_peak,retained)}}
   else {c.cache+=4;sf.set(s,(sf.get(s)||0)+1);tf.set(t,(tf.get(t)||0)+1);if(tf.get(t)>=3&&tf.get(t)>sf.get(s)){if(!b)b=build(true);c.reverse_queries++;p=cached(rw,b,t,s,true)}else p=cached(fw,a,s,t,false)}
   c.witness+=p?Math.max(0,p.length-1):0;answers.push(p)
  }
  return {c,answers}
 }
 for(const f of families)for(let k=0;k<16;k++){
  const seed=91001+families.indexOf(f)*1000+k,g=graph(f,k),w=workloads[k%4],qs=queryList(g,seed,w);
  const truth=qs.map(([s,t])=>oracle({...g,s,t})),validEdges=new Set(g.edges.filter(e=>e[2]).map(e=>e[0]+":"+e[1]));
  const rec={family:f,workload:w,seed,nodes:g.meta.length,edges:g.edges.length,queries:qs,oracle:truth,methods:{}};
  for(const m of methods){const {c,answers}=execute(g,qs,m);for(let i=0;i<qs.length;i++){let p=answers[i],valid=!p||p[0]===qs[i][0]&&p.at(-1)===qs[i][1]&&p.slice(1).every((v,j)=>validEdges.has(p[j]+":"+v));c.invalid+=+!valid;c.correct+=+(valid&&(p?p.length-1:null)===truth[i])}
   rec.methods[m]={...c,total:cost(c)};for(const a of [totals[m],by_family[f][m],by_workload[w][m]])for(const key in c)a[key]+=c[key];
  }cases.push(rec)
 }
 const comparison=x=>{let costs=Object.fromEntries(methods.map(m=>[m,cost(x[m])]));let best=methods.filter(m=>m!=="selective").sort((a,b)=>costs[a]-costs[b])[0];return {costs,best_baseline:best,vs_forward:1-costs.selective/costs.filtered_forward,vs_best:1-costs.selective/costs[best]}};
 const comparisons={all:comparison(totals),by_family:Object.fromEntries(families.map(f=>[f,comparison(by_family[f])])),by_workload:Object.fromEntries(workloads.map(w=>[w,comparison(by_workload[w])]))};
 const primary=methods.every(m=>totals[m].correct===3072&&totals[m].invalid===0),secondary=comparisons.all.vs_forward>=.2&&comparisons.all.vs_best>=0;
 return {id:"JANUS-CHRONO-DNA-R2-SELECTIVE-REPLICATION",protocol_commit:"51d9aa9c01a6ca4e5abb75320d9a579563612ae2",status:primary&&secondary?"SYNTHETIC_WORK_GATE_PASS__EXTERNAL_HOLD":primary?"CORRECTNESS_PASS__EFFICIENCY_HOLD":"CORRECTNESS_FAIL",primary,secondary,graphs:cases.length,queries:3072,reachable:cases.reduce((s,x)=>s+x.oracle.filter(v=>v!==null).length,0),totals,comparisons,by_family,by_workload,cases,limitations:["No real JANUS module execution, synthetic online query workload","Costs are declared abstract operations; not runtime or memory bytes","Space_peak sums per-graph peaks, not simultaneous global peak","Uncharged JS allocation, map internal costs and path reconstruction overhead; no mutation workload","Unique mixed attempts distinct pairs up to 128 retries; very small graphs may repeat"]};
}
console.log(JSON.stringify(run(graph,oracle,families),null,2));
