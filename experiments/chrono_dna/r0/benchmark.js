// Deterministic CHRONO-DNA R0; run with node benchmark.js
function benchmark(){
  const families=["balanced","forward_fanout","reverse_fanout","dense","chain","cyclic"];
  function graph(f,k){
    let seed=26001+families.indexOf(f)*1000+k;
    function rand(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296}
    const pick=n=>Math.floor(rand()*n), depth=8+pick(7), positive=k%2===0;
    const layers=[], meta=[], edges=[], seen=new Set();
    for(let l=0;l<=depth;l++){
      let width=l===0||l===depth?1:f==="chain"?1:f==="dense"?22+pick(8):f==="forward_fanout"?Math.min(65,2+Math.floor(4*Math.pow(l,1.25))):f==="reverse_fanout"?Math.min(65,2+Math.floor(4*Math.pow(depth-l,1.25))):12+pick(15);
      layers[l]=[];for(let i=0;i<width;i++){let id=meta.length;layers[l].push(id);meta.push([l,pick(5),pick(6),pick(20),pick(4)])}
    }
    const cut=Math.floor(depth/2), s=0,t=meta.length-1;
    function add(u,v,valid){let key=u+":"+v;if(seen.has(key))return;seen.add(key);if(!positive&&meta[u][0]<=cut&&meta[v][0]>cut)valid=false;edges.push([u,v,valid])}
    const spine=layers.map(a=>a[pick(a.length)]);
    if(positive)for(let l=0;l<depth;l++)add(spine[l],spine[l+1],true);
    for(let l=0;l<depth;l++)for(const u of layers[l]){
      let b=layers[l+1],degree=f==="dense"?b.length:f==="chain"?1:f==="forward_fanout"?5:f==="reverse_fanout"?3:2+pick(5);
      if(f==="dense")for(const v of b)add(u,v,rand()<.85);
      else for(let j=0;j<degree;j++)add(u,b[pick(b.length)],rand()<.88);
      if(f==="cyclic"){for(let j=0;j<2;j++)add(u,layers[l][pick(layers[l].length)],rand()<.85);if(l>0)add(u,layers[l-1][pick(layers[l-1].length)],rand()<.85)}
    }
    // Fixed random ordering for all consumers.
    for(let i=edges.length-1;i>0;i--){let j=pick(i+1);[edges[i],edges[j]]=[edges[j],edges[i]]}
    return {meta,edges,s,t,positive};
  }
  function oracle(g){let d=Array(g.meta.length).fill(Infinity);d[g.s]=0;for(let j=0;j<g.meta.length-1;j++){let change=false;for(const [u,v,ok] of g.edges)if(ok&&d[u]+1<d[v]){d[v]=d[u]+1;change=true}if(!change)break}return Number.isFinite(d[g.t])?d[g.t]:null}
  function search(g,method){
    let stats={inspections:0,expanded:0,rank_evaluations:0,sort_comparisons:0,index_passes:0,witness_edges:0};
    const n=g.meta.length, a=Array.from({length:n},()=>[]), b=Array.from({length:n},()=>[]), dbl=method==="double";
    for(const [u,v,ok] of g.edges){stats.index_passes++;a[u].push([v,ok])}
    if(dbl)for(const [u,v,ok] of g.edges){stats.index_passes++;b[v].push([u,ok])}
    let pf=new Map([[g.s,null]]),pr=new Map([[g.t,null]]),df=new Map([[g.s,0]]),dr=new Map([[g.t,0]]);
    function path(m){let p=[],u=m;while(u!==null){p.push(u);u=pf.get(u)}p.reverse();if(dbl){u=pr.get(m);while(u!==null){p.push(u);u=pr.get(u)}}return p}
    function finish(p){stats.witness_edges=p?Math.max(0,p.length-1):0;return {p,stats}}
    if(!dbl){let q=[g.s],head=0;while(head<q.length){let u=q[head++];if(u===g.t)return finish(path(u));stats.expanded++;let candidates=[];for(const [v,ok] of a[u]){stats.inspections++;if(ok&&!pf.has(v))candidates.push(v)}
      if(method==="single"){
        let target=g.meta[g.t];let scored=candidates.map(v=>{let x=g.meta[v];stats.rank_evaluations++;return [v,[Math.abs(x[0]-target[0]),+(x[1]!==target[1]),Math.abs(x[2]-target[2]),Math.abs(x[3]-target[3]),-x[4]]]});
        scored.sort((x,y)=>{stats.sort_comparisons++;for(let i=0;i<5;i++){let d=x[1][i]-y[1][i];if(d)return d}return x[0]-y[0]});candidates=scored.map(x=>x[0])
      }
      for(let v of candidates){if(pf.has(v))continue;pf.set(v,u);q.push(v)}
    }return finish(null)}
    let f=[g.s],rev=[g.t];
    while(f.length&&rev.length){
      let forward=f.length<=rev.length, frontier=forward?f:rev,adj=forward?a:b,parents=forward?pf:pr,own=forward?df:dr,other=forward?dr:df;
      let next=[],meet=null,best=Infinity;
      for(const u of frontier){stats.expanded++;for(const [v,ok] of adj[u]){stats.inspections++;if(!ok||own.has(v))continue;parents.set(v,u);own.set(v,own.get(u)+1);next.push(v);if(other.has(v)){let len=own.get(v)+other.get(v);if(len<best){best=len;meet=v}}}}
      if(meet!==null)return finish(path(meet));
      if(forward)f=next;else rev=next;
    }return finish(null)
  }
  const methods=["forward","single","double"], cases=[], sums={};
  for(let f of families){sums[f]={};for(let m of methods)sums[f][m]={correct:0,invalid:0,inspections:0,expanded:0,rank_evaluations:0,sort_comparisons:0,index_passes:0,witness_edges:0};for(let k=0;k<24;k++){
    let g=graph(f,k),truth=oracle(g),validEdges=new Set(g.edges.filter(x=>x[2]).map(x=>x[0]+":"+x[1]));if((truth!==null)!==g.positive)throw Error("generator truth");
    let entry={family:f,seed:26001+families.indexOf(f)*1000+k,nodes:g.meta.length,edges:g.edges.length,oracle:truth,methods:{}};
    for(let m of methods){let {p,stats}=search(g,m);let len=p?p.length-1:null;let valid=!p||(p[0]===g.s&&p[p.length-1]===g.t&&p.slice(1).every((v,i)=>validEdges.has(p[i]+":"+v)));let correct=len===truth&&valid;entry.methods[m]={length:len,correct,valid,...stats};let s=sums[f][m];s.correct+=+correct;s.invalid+=+!valid;for(let key of Object.keys(stats))s[key]+=stats[key]}
    cases.push(entry)
  }}
  let totals={};for(let m of methods){totals[m]={};for(let key of Object.keys(sums[families[0]][m]))totals[m][key]=families.reduce((v,f)=>v+sums[f][m][key],0)}
  const cold=x=>x.inspections+x.index_passes+x.witness_edges, warm=x=>x.inspections+x.witness_edges;
  const comparisons={};for(let f of [...families,"all"]){let x=f==="all"?totals:sums[f];comparisons[f]={search_reduction:1-x.double.inspections/x.forward.inspections,cold_reduction:1-cold(x.double)/cold(x.forward),warm_reduction:1-warm(x.double)/warm(x.forward),single_search_reduction:1-x.single.inspections/x.forward.inspections}}
  let primary=methods.every(m=>totals[m].correct===144&&totals[m].invalid===0),secondary=comparisons.all.search_reduction>=.2;
  return {id:"JANUS-CHRONO-DNA-R0",status:primary&&secondary?"SYNTHETIC_SEARCH_GATE_PASS__EXTERNAL_HOLD":primary?"CORRECTNESS_PASS__EFFICIENCY_HOLD":"CORRECTNESS_FAIL",protocol_commit:"641d250483f552da66aa8ef03f2e7f04a4ffb3a6",case_count:cases.length,positive_cases:cases.filter(x=>x.oracle!==null).length,primary_gate:primary,secondary_gate:secondary,totals,by_family:sums,comparisons,limits:["single is a five-axis-inspired ordering proxy, not full recursive 5D","double is conventional bidirectional BFS, not a novel physical or biological mechanism","cold work counts edge passes and witness edges only; rank and sort counters separate; no timing claim","oracle and witness validation reference preparation excluded symmetrically from search work","no independent external evaluation or production adoption"],cases}
}
console.log(JSON.stringify(benchmark(),null,2));
