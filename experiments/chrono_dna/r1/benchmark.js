// R1 fixed-seed benchmark, Node.js; generator derived from R0
const families=["balanced","forward_fanout","reverse_fanout","dense","chain","cyclic","tree_like","bottleneck"];
  function graph(f,k){
    let seed=61001+families.indexOf(f)*1000+k;
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
 const methods=["forward","r0","adaptive","vascular","filtered_forward","filtered_r0","reverse"];
 function search(g,m){
  const n=g.meta.length, a=Array.from({length:n},()=>[]), b=Array.from({length:n},()=>[]);
  const filter=["vascular","filtered_forward","filtered_r0"].includes(m), bidir=["r0","adaptive","vascular","filtered_r0"].includes(m), reverse=m==="reverse", adaptive=["adaptive","vascular"].includes(m);
  const c={inspections:0,expanded:0,routing:0,index:0,witness:0};
  if(!reverse)for(const [u,v,ok] of g.edges){c.index++;if(!filter||ok)a[u].push([v,ok]);}
  if(bidir||reverse)for(const [u,v,ok] of g.edges){c.index++;if(!filter||ok)b[v].push([u,ok]);}
  const pf=new Map([[g.s,null]]),pr=new Map([[g.t,null]]),df=new Map([[g.s,0]]),dr=new Map([[g.t,0]]);
  const path=(meet)=>{const p=[];let u=meet;if(!reverse){while(u!==null){p.push(u);u=pf.get(u)}p.reverse()}else p.push(meet);if(bidir||reverse){u=pr.get(meet);while(u!==null){p.push(u);u=pr.get(u)}}return p};
  const finish=p=>{c.witness=p?p.length-1:0;return {p,c}};
  if(!bidir){const adj=reverse?b:a,parent=reverse?pr:pf,start=reverse?g.t:g.s,target=reverse?g.s:g.t,q=[start];for(let h=0;h<q.length;h++){const u=q[h];c.expanded++;for(const [v,ok] of adj[u]){c.inspections++;if(!ok||parent.has(v))continue;parent.set(v,u);if(v===target)return finish(path(v));q.push(v)}}return finish(null)}
  let f=[g.s],rev=[g.t];
  while(f.length&&rev.length){
   let forward=f.length<=rev.length;
   if(adaptive){let fc=0,rc=0;for(const u of f){c.routing++;fc+=a[u].length}for(const u of rev){c.routing++;rc+=b[u].length}forward=fc<=rc;}
   const frontier=forward?f:rev,adj=forward?a:b,parents=forward?pf:pr,own=forward?df:dr,other=forward?dr:df;
   let next=[],meet=null,best=Infinity;
   for(const u of frontier){c.expanded++;for(const [v,ok] of adj[u]){c.inspections++;if(!ok||own.has(v))continue;parents.set(v,u);own.set(v,own.get(u)+1);next.push(v);if(other.has(v)){let d=own.get(v)+other.get(v);if(d<best){meet=v;best=d}}}}
   if(meet!==null)return finish(path(meet));if(forward)f=next;else rev=next;
  }return finish(null)
 }
 const blank=()=>({correct:0,invalid:0,inspections:0,expanded:0,routing:0,index:0,witness:0});
 let cases=[],totals=Object.fromEntries(methods.map(m=>[m,blank()])),by_family={};
 for(const f of families){let group=Object.fromEntries(methods.map(m=>[m,blank()]));by_family[f]=group;
  for(let k=0;k<32;k++){const g=graph(f,k),truth=oracle(g);if((truth!==null)!==g.positive)throw Error("generator truth");const edges=new Set(g.edges.filter(e=>e[2]).map(e=>e[0]+":"+e[1]));const rec={family:f,seed:61001+families.indexOf(f)*1000+k,nodes:g.meta.length,edges:g.edges.length,oracle:truth,methods:{}};
   for(const m of methods){let {p,c}=search(g,m);let valid=!p||p[0]===g.s&&p.at(-1)===g.t&&p.slice(1).every((v,i)=>edges.has(p[i]+":"+v));let length=p?p.length-1:null,correct=valid&&length===truth;rec.methods[m]={correct,valid,length,...c};for(let acc of [totals[m],group[m]]){acc.correct+=+correct;acc.invalid+=+!valid;for(const key in c)acc[key]+=c[key]}}
   cases.push(rec)
  }
 }
 const warm=x=>x.inspections+x.routing+x.witness,cold=x=>warm(x)+x.index;
 const compare=(x,m,b)=>({search:1-x[m].inspections/x[b].inspections,warm:1-warm(x[m])/warm(x[b]),cold:1-cold(x[m])/cold(x[b])});
 const comparisons={};for(const f of [...families,"all"]){const x=f==="all"?totals:by_family[f];comparisons[f]={vascular_vs_forward:compare(x,"vascular","forward"),vascular_vs_filtered_forward:compare(x,"vascular","filtered_forward"),vascular_vs_filtered_r0:compare(x,"vascular","filtered_r0"),adaptive_vs_r0:compare(x,"adaptive","r0"),vascular_vs_reverse:compare(x,"vascular","reverse")}}
 const primary=methods.every(m=>totals[m].correct===256&&totals[m].invalid===0),secondary=comparisons.all.vascular_vs_forward.search>=.2;
 return {id:"JANUS-CHRONO-DNA-R1-VASCULAR-HELIX",protocol_commit:"0e968cdb3eb75ffa607e6d06fe64c75522e3046f",status:primary&&secondary?"SYNTHETIC_SEARCH_GATE_PASS__EXTERNAL_HOLD":primary?"CORRECTNESS_PASS__EFFICIENCY_HOLD":"CORRECTNESS_FAIL",primary,secondary,total_cases:cases.length,totals,by_family,comparisons,cases,limits:["New seeds but first six generator families related to R0; no independent custody","ROWAN and PHYSARIUS architectural proxies, not native executions","No physical time, protein fitness, wall-clock or production claim","Index charges raw edge passes; warm cost includes routing and witness; other bookkeeping not timed"]};
}
console.log(JSON.stringify(run(graph,oracle,families),null,2));
